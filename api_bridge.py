from datetime import datetime
from flask import Flask, request, jsonify
import os
import json
import requests
from startsetup import *
from scanner import *
from flask_cors import CORS
import platform
import getpass
import asyncio  
from sender_api_functions import quic_connect, send_file, close_connection 
from pki.store import PeerStore
from pki.utils import fingerprint_pem, load_cert_pem


app = Flask(__name__)

CHUNK_SIZE = 64 * 1024
ENV_FILE = ".env"
CORS(app, resources={r"/*": {"origins":"*"}})

# Transfer task registry for progress tracking
import uuid
from threading import Lock

_transfer_tasks = {}  # task_id -> {status, progress, total_size, transferred, files, error}
_transfer_lock = Lock()


def _create_transfer_task(files: list, remote_host: str, direction: str = "send") -> str:
    """Create a new transfer task and return its ID."""
    task_id = str(uuid.uuid4())
    total_size = 0
    for f in files:
        if os.path.isfile(f):
            total_size += os.path.getsize(f)
    
    with _transfer_lock:
        _transfer_tasks[task_id] = {
            "status": "in_progress",
            "progress": 0.0,
            "total_size": total_size,
            "transferred": 0,
            "files": files,
            "remote_host": remote_host,
            "direction": direction,
            "error": None,
            "current_file": files[0] if files else None,
        }
    return task_id


def _update_transfer_progress(task_id: str, bytes_sent: int, total_bytes: int):
    """Update transfer progress (called from sender)."""
    with _transfer_lock:
        if task_id in _transfer_tasks:
            task = _transfer_tasks[task_id]
            task["transferred"] = bytes_sent
            if total_bytes > 0:
                task["progress"] = min(bytes_sent / total_bytes, 1.0)


def _complete_transfer_task(task_id: str, success: bool, error: str = None):
    """Mark a transfer task as completed or failed."""
    with _transfer_lock:
        if task_id in _transfer_tasks:
            task = _transfer_tasks[task_id]
            task["status"] = "completed" if success else "failed"
            task["progress"] = 1.0 if success else task["progress"]
            task["error"] = error


import threading

class PeerDiscoveryResponder(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        self.discovery_port = 4436
        self.discovery_msg = b"WHO_IS_PEER"
        self.response_prefix = b"I_AM_PEER"
        env = load_env_vars()
        self.host_ip = env.get("host", "0.0.0.0")

    def run(self):
        print(f"[*] Starting Peer Discovery Responder on UDP {self.discovery_port}...")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # On Linux, SO_REUSEPORT allows multiple processes to bind to the same port
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except AttributeError:
                pass # Not available on all platforms
                
            try:
                sock.bind(('0.0.0.0', self.discovery_port))
            except Exception as e:
                print(f"[!] Peer Discovery Bind Failed: {e}")
                return

            while self.running:
                try:
                    data, addr = sock.recvfrom(1024)
                    if data == self.discovery_msg:
                        # Respond with I_AM_PEER <HOST_IP>
                        response = f"{self.response_prefix.decode()} {self.host_ip}".encode()
                        sock.sendto(response, addr)
                except Exception as e:
                    print(f"[!] Peer Discovery Error: {e}")

def start_peer_discovery():
    try:
        t = PeerDiscoveryResponder()
        t.start()
    except Exception as e:
        print(f"[-] Failed to start peer discovery: {e}")


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200


@app.route("/listhost", methods=["GET"])
def listhost():
    """List available hosts in subnet"""
    env = load_env_vars()
    host = env["host"]
    
    host_list = gethostlist()
    
    # print(host_list)
    

    return jsonify(host_list)



@app.route("/osinfo", methods=["POST"])
def osinfo():
    """Return OS and user info for this peer"""
    try:
        os_name = platform.system().lower()
        user_name = getpass.getuser()
        print(f"OS Info Requested: OS={os_name}, User={user_name}")
        return jsonify({"os": os_name, "user": user_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/listdir', methods=['POST'])
def list_directory():
    """
    List directory contents on THIS peer
    POST body: {"path": "/absolute/path"}
    """
    try:
        data = request.get_json(silent=True) or {}
        path = data.get("path")

        if not path:
            return jsonify({"status": "error", "message": "path is required"}), 400

        remote_host = data.get("remote_host")
        # Check if we need to proxy this request
        if remote_host:
             # If remote_host is THIS machine, treat as local
            env = load_env_vars()
            my_ip = env.get("host")
            
            if remote_host != my_ip and remote_host != "127.0.0.1" and remote_host != "localhost":
                 print(f"[*] Proxying listdir request for {path} to {remote_host}")
                 try:
                     # Proxy the request to the remote host
                     # We forward the same payload but WITHOUT the remote_host field to prevent infinite loops
                     # in case of misconfiguration, although the check above prevents immediate self-loop.
                     
                     proxy_payload = {"path": path} # Only send path
                     
                     resp = requests.post(
                         f"http://{remote_host}:5000/listdir",
                         json=proxy_payload,
                         timeout=10
                     )
                     
                     if resp.status_code == 200:
                         return jsonify(resp.json()), 200
                     else:
                         return jsonify({
                             "status": "error", 
                             "message": f"Remote host returned {resp.status_code}: {resp.text}"
                         }), resp.status_code
                         
                 except requests.exceptions.RequestException as e:
                     print(f"[!] Proxy failed: {e}")
                     return jsonify({
                         "status": "error", 
                         "message": f"Failed to contact remote host {remote_host}: {str(e)}"
                     }), 502

        path = os.path.normpath(path)

        if not os.path.exists(path):
            return jsonify({
                "status": "error",
                "message": f"Path does not exist: {path}"
            }), 404

        # ---------------- FILE ----------------
        if os.path.isfile(path):
            st = os.stat(path)
            info = {
                "name": os.path.basename(path),
                "path": path,
                "is_directory": False,
                "size": st.st_size,
                "mtime": datetime.utcfromtimestamp(st.st_mtime).isoformat() + "Z",
            }
            return jsonify({
                "status": "success",
                "type": "file",
                "info": info
            }), 200

        # --------------- DIRECTORY ---------------
        if os.path.isdir(path):
            files = []

            try:
                entries = sorted(os.listdir(path))
            except PermissionError:
                return jsonify({
                    "status": "error",
                    "message": "Permission denied"
                }), 403

            for name in entries:
                full_path = os.path.join(path, name)

                try:
                    st = os.stat(full_path)
                    is_dir = os.path.isdir(full_path)

                    files.append({
                        "name": name,
                        "path": full_path,
                        "is_directory": is_dir,
                        "size": None if is_dir else st.st_size,
                        "mtime": datetime.utcfromtimestamp(
                            st.st_mtime
                        ).isoformat() + "Z",
                    })
                except PermissionError:
                    # Skip unreadable entries silently
                    continue
                except FileNotFoundError:
                    # Race condition (deleted between list/stat)
                    continue

            return jsonify({
                "status": "success",
                "type": "directory",
                "files": files
            }), 200

        return jsonify({
            "status": "error",
            "message": f"Unknown filesystem object: {path}"
        }), 400

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500



@app.route("/send_files", methods=["POST"])
def send_files():
    data = request.get_json() or {}
    files = data.get("files", [])
    remote_host = data.get("remote_host")
    
    if not isinstance(files, list) or not files:
        return jsonify({"status": "error", "message": "files must be a non-empty list"}), 400

    env = load_env_vars()
    if not remote_host:
        remote_host = env.get("dest_host") or env.get("recivhost") or env.get("host")

    if not remote_host:
        return jsonify({"status": "error", "message": "remote_host or DEST_HOST/HOST not set"}), 400

    port = env.get("port") or 4433

    # verify files exist
    valid_files = []
    missing = []
    for f in files:
        if os.path.isfile(f):
            valid_files.append(f)
        else:
            missing.append(f)

    if not valid_files:
        return jsonify({"status": "error", "message": "no valid files to send", "missing": missing}), 400

    # Create task for tracking
    task_id = _create_transfer_task(valid_files, remote_host, "send")
    
    def _do_send_background():
        """Background thread to perform the actual transfer."""
        try:
            client_cert = env.get("CLIENT_CERT")
            client_key = env.get("CLIENT_KEY")
            ca_cert = env.get("CA_CERT") or env.get("ca_cert")

            if not ca_cert:
                _complete_transfer_task(task_id, False, "CA_CERT not set")
                return

            async def _async_send():
                from sender_api_functions import send_file_with_progress
                
                conn = await quic_connect(
                    host=remote_host,
                    port=port,
                    insecure=False,
                    server_name=os.environ.get("SERVER_NAME"),
                    client_cert=client_cert,
                    client_key=client_key,
                    ca_cert=ca_cert,
                )
                try:
                    # Calculate total size for all files
                    total_size = sum(os.path.getsize(f) for f in valid_files)
                    bytes_sent_total = 0
                    
                    for path in valid_files:
                        # Update current file in task
                        with _transfer_lock:
                            if task_id in _transfer_tasks:
                                _transfer_tasks[task_id]["current_file"] = path
                        
                        file_size = os.path.getsize(path)
                        
                        def on_progress(bytes_sent_file):
                            nonlocal bytes_sent_total
                            current_total = bytes_sent_total + bytes_sent_file
                            _update_transfer_progress(task_id, current_total, total_size)
                        
                        await send_file_with_progress(conn, path, on_progress)
                        bytes_sent_total += file_size
                    
                    _complete_transfer_task(task_id, True)
                finally:
                    await close_connection(conn)

            asyncio.run(_async_send())
            
        except Exception as e:
            print(f"[send_files] Transfer error: {e}")
            _complete_transfer_task(task_id, False, str(e))

    # Start transfer in background thread
    thread = threading.Thread(target=_do_send_background, daemon=True)
    thread.start()

    # Return immediately with task_id for polling
    return jsonify({
        "status": "in_progress",
        "task_id": task_id,
        "remote_host": remote_host,
        "port": port,
        "files": valid_files,
        "missing": missing
    }), 202  # 202 Accepted


@app.route("/transfer_status/<task_id>", methods=["GET"])
def transfer_status(task_id):
    """Get the status of a transfer task."""
    with _transfer_lock:
        if task_id not in _transfer_tasks:
            return jsonify({"status": "error", "message": "Task not found"}), 404
        
        task = _transfer_tasks[task_id].copy()
    
    return jsonify({
        "status": task["status"],
        "progress": task["progress"],
        "total_size": task["total_size"],
        "transferred": task["transferred"],
        "files": task["files"],
        "current_file": task.get("current_file"),
        "error": task["error"],
    }), 200



@app.route("/receive_files", methods=["POST"])
def receive_files():
    # try:
    data = request.get_json() or {}
    remote_host = data.get("remote_host")
    files = data.get("files", [])
    
    if not remote_host:
        return jsonify({"status": "error", "message": "remote_host is required"}), 400
        
    if not isinstance(files, list) or not files:
        return jsonify({"status": "error", "message": "files must be a non-empty list"}), 400

    env = load_env_vars()
    our_host = env.get("host")
    
    if not our_host:
        return jsonify({"status": "error", "message": "Cannot determine local host IP"}), 500

    try:
        response = requests.post(
            f"http://{remote_host}:5000/send_files",
            json={
                "remote_host": our_host,  
                "files": files            # Files on REMOTE system
            },
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            return jsonify({
                "status": "success",
                "message": f"Requested {len(files)} file(s) from {remote_host}",
                "remote_response": result
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": f"Remote peer returned error: {response.text}"
            }), response.status_code
            
    except requests.RequestException as e:
        return jsonify({
            "status": "error",
            "message": f"Failed to contact remote peer: {str(e)}"
        }), 500

    # except Exception as e:
    #     return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/peers', methods=['GET'])
def list_peers():
    """List known peers and their trust status."""
    try:
        store = PeerStore()
        peers = store.list_peers()
        return jsonify({"status": "success", "peers": peers}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/pki/info", methods=["GET"])
def pki_info():
    ca_path = os.environ.get("CA_CERT")
    if ca_path and os.path.exists(ca_path):
        pem = open(ca_path).read()
        return {
            "has_ca": True,
            "fingerprint": fingerprint_pem(pem)
        }, 200
    return {"has_ca": False}, 200



@app.route("/pki/ca", methods=["GET"])
def fetch_ca():
    ca_path = os.environ.get("CA_CERT")
    if not ca_path or not os.path.exists(ca_path):
        return {"error": "CA not initialized"}, 404
    return send_file(ca_path)


@app.route('/peers/approve', methods=['POST'])
def approve_peer():
    try:
        data = request.get_json() or {}
        fp = data.get('fingerprint')
        password = data.get('password')
        if not fp:
            return jsonify({'status': 'error', 'message': 'fingerprint required'}), 400
        store = PeerStore()
        store.approve_peer(fp, password=password)
        return jsonify({'status': 'success', 'fingerprint': fp}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/peers/reject', methods=['POST'])
def reject_peer():
    try:
        data = request.get_json() or {}
        fp = data.get('fingerprint')
        if not fp:
            return jsonify({'status': 'error', 'message': 'fingerprint required'}), 400
        store = PeerStore()
        store.reject_peer(fp)
        return jsonify({'status': 'success', 'fingerprint': fp}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/peers/verify', methods=['POST'])
def verify_peer_password():
    try:
        data = request.get_json() or {}
        fp = data.get('fingerprint')
        password = data.get('password')
        if not fp or not password:
            return jsonify({'status': 'error', 'message': 'fingerprint and password required'}), 400
        store = PeerStore()
        ok = store.verify_password(fp, password)
        return jsonify({'status': 'success', 'verified': bool(ok)}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/handshake', methods=['POST'])
def handshake():
    try:
        data = request.get_json() or {}
        dest_host = data.get('dest_host')
        password = data.get('password')
        
        if not dest_host:
            return jsonify({'success': False, 'error': 'dest_host is required'}), 400
        
        if not password:
            return jsonify({'success': False, 'error': 'password is required'}), 400
        
        # Get environment for certificate paths
        env = load_env_vars()
        client_cert = env.get('certi') or 'cert.pem'
        ca_cert = env.get('ca_cert') or 'ca_cert.pem'
        
        # Check if certificates exist
        if not os.path.isfile(client_cert):
            return jsonify({
                'success': False,
                'error': f'Client certificate not found: {client_cert}'
            }), 500
        
        if not os.path.isfile(ca_cert):
            return jsonify({
                'success': False,
                'error': f'CA certificate not found: {ca_cert}'
            }), 500
        
        # Perform handshake asynchronously
        from pki.handshake import initiate_handshake
        
        async def _do_handshake():
            return await initiate_handshake(
                dest_host=dest_host,
                password=password,
                client_cert_path=client_cert,
                ca_cert_path=ca_cert
            )
        
        success = asyncio.run(_do_handshake())
        
        if success:
            return jsonify({'success': True}), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Authentication failed. Check password or peer availability.'
            }), 401
        
    except Exception as e:
        print(f"[!] Handshake error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500



if __name__ == "__main__":
    start_peer_discovery()
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        # use_reloader=False
    )
