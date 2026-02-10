from datetime import datetime
from flask import Flask, request, jsonify, send_file as flask_send_file
import os
import json
import requests
import platform
import getpass
import asyncio
import sys
from pathlib import Path

# CRITICAL: Set up paths FIRST, before importing any local modules
APP_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(APP_DIR))

# Now import local modules - using AppConfig for centralized configuration
from app_config import get_config, AppConfig
from startsetup import load_env_vars  # Keep for backward compatibility
from scanner import gethostlist, start_peer_discovery_listener
from sender_api_functions import quic_connect, send_file as quic_send_file, close_connection
from pki.store import PeerStore
from pki.utils import fingerprint_pem, load_cert_pem
from path_security import (
    get_lanfxplorer_root,
    validate_path_access,
    is_path_within_root,
    is_path_at_minimum_depth,
    ensure_lanfxplorer_directory
)


app = Flask(__name__)

CHUNK_SIZE = 64 * 1024
ENV_FILE = ".env"
# CORS(app, resources={r"/*": {"origins":"*"}})

# Transfer task registry for progress tracking
import uuid
import time
from threading import Lock
from wifi_speed import estimate_transfer_time_seconds, get_wifi_speed

# ==================== PATH RESTRICTION HELPERS ====================
# Path security functions imported from path_security module
# get_lanfxplorer_root(), validate_path_access(), is_path_within_root(),
# is_path_at_minimum_depth() are all imported at the top of this file.

def get_root_path():
    """Get the configured root path - uses Lanfxplorer directory."""
    return get_lanfxplorer_root()

# ==================================================================

_transfer_tasks = {}  # task_id -> {status, progress, total_size, transferred, files, error, start_time, estimated_duration}

# Mapping of task_id -> remote_host for fetch operations that need to proxy status requests
_fetch_task_mapping = {}  # task_id -> {"remote_host": str, "remote_task_id": str}

_transfer_lock = Lock()

# Cache WiFi speed (detect once at startup or first transfer)
_wifi_speed_mbps = None

def _get_cached_wifi_speed():
    """Get cached WiFi speed or detect it."""
    global _wifi_speed_mbps
    if _wifi_speed_mbps is None:
        _wifi_speed_mbps = get_wifi_speed()
        if _wifi_speed_mbps:
            print(f"[wifi_speed] Detected: {_wifi_speed_mbps} Mbps")
        else:
            print("[wifi_speed] Could not detect, using fallback 100 Mbps")
            _wifi_speed_mbps = 100  # Fallback
    return _wifi_speed_mbps


def _create_transfer_task(files: list, remote_host: str, direction: str = "send") -> str:
    """Create a new transfer task and return its ID."""
    task_id = str(uuid.uuid4())
    total_size = 0
    for f in files:
        if os.path.isfile(f):
            total_size += os.path.getsize(f)
    
    # Calculate estimated duration based on WiFi speed
    wifi_speed = _get_cached_wifi_speed()
    estimated_duration = estimate_transfer_time_seconds(total_size, wifi_speed)
    
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
            "start_time": time.time(),
            "estimated_duration": estimated_duration,
            "wifi_speed_mbps": wifi_speed,
        }
    print(f"[transfer] Task {task_id[:8]}... created: {total_size/(1024*1024):.1f}MB, ETA: {estimated_duration:.1f}s at {wifi_speed}Mbps")
    return task_id


def _update_transfer_progress(task_id: str, bytes_sent: int, total_bytes: int):
    """Update transfer progress based on elapsed time (simulated realistic progress)."""
    with _transfer_lock:
        if task_id in _transfer_tasks:
            task = _transfer_tasks[task_id]
            task["transferred"] = bytes_sent
            
            # Calculate progress based on elapsed time vs estimated duration
            # This gives smoother, more realistic progress
            if task["estimated_duration"] > 0:
                elapsed = time.time() - task["start_time"]
                task["progress"] = min(elapsed / task["estimated_duration"], 0.99)  # Cap at 99% until complete
            elif total_bytes > 0:
                task["progress"] = min(bytes_sent / total_bytes, 0.99)


def _complete_transfer_task(task_id: str, success: bool, error: str = None):
    """Mark a transfer task as completed or failed."""
    with _transfer_lock:
        if task_id in _transfer_tasks:
            task = _transfer_tasks[task_id]
            task["status"] = "completed" if success else "failed"
            task["progress"] = 1.0 if success else task["progress"]
            task["error"] = error
            
            # Log actual vs estimated time
            actual_duration = time.time() - task["start_time"]
            print(f"[transfer] Task {task_id[:8]}... {'completed' if success else 'failed'}: "
                  f"actual={actual_duration:.1f}s, estimated={task['estimated_duration']:.1f}s")


import threading

# ==================== DEPRECATED: Threading-based Peer Discovery ====================
# NOTE: This threading-based implementation is DEPRECATED.
# The canonical peer discovery is the asyncio-based PeerDiscoveryListener in scanner.py
# which is started by receive.py. This class is kept for reference/backup only.
# ===================================================================================
class PeerDiscoveryResponder(threading.Thread):
    """DEPRECATED: Use PeerDiscoveryListener from scanner.py instead."""
    
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        self.discovery_port = AppConfig.PEER_DISCOVERY_PORT
        self.discovery_msg = AppConfig.PEER_DISCOVERY_MSG
        self.response_prefix = AppConfig.PEER_RESPONSE_PREFIX
        config = get_config()
        self.host_ip = config.host or "0.0.0.0"

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
    """DEPRECATED: Peer discovery is now handled by asyncio-based listener in scanner.py."""
    print("[!] WARNING: start_peer_discovery() is deprecated. Using asyncio listener in receive.py instead.")
    # Keeping code but not starting it - asyncio version is canonical
    # try:
    #     t = PeerDiscoveryResponder()
    #     t.start()
    # except Exception as e:
    #     print(f"[-] Failed to start peer discovery: {e}")
    pass


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


@app.route("/default_path", methods=["GET", "POST"])
def default_path():
    """
    Return the default path (Lanfxplorer root) for this peer.
    This allows remote peers to know where to start browsing files.
    
    Can also proxy to remote host if remote_host is provided in POST body.
    """
    try:
        data = request.get_json(silent=True) or {}
        remote_host = data.get("remote_host")
        
        # If remote_host is provided, proxy the request
        if remote_host:
            env = load_env_vars()
            my_ip = env.get("host")
            
            if remote_host != my_ip and remote_host != "127.0.0.1" and remote_host != "localhost":
                print(f"[*] Proxying default_path request to {remote_host}")
                try:
                    resp = requests.get(
                        f"http://{remote_host}:5000/default_path",
                        timeout=10
                    )
                    if resp.status_code == 200:
                        return jsonify(resp.json()), 200
                    else:
                        return jsonify({
                            "status": "error",
                            "message": f"Remote host returned {resp.status_code}"
                        }), resp.status_code
                except requests.exceptions.RequestException as e:
                    return jsonify({
                        "status": "error",
                        "message": f"Failed to contact remote host: {str(e)}"
                    }), 502
        
        # Return the Lanfxplorer root path
        root = get_lanfxplorer_root()
        
        # Ensure directory exists
        ensure_lanfxplorer_directory()
        
        return jsonify({
            "status": "success",
            "default_path": root
        }), 200
        
    except Exception as e:
        print(f"[!] Error getting default path: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/listdir', methods=['POST'])
def list_directory():
    """
    List directory contents on THIS peer
    POST body: {"path": "/absolute/path"}
    """
    # try:
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

    # ========== PATH RESTRICTION CHECK ==========
    is_valid, error_msg = validate_path_access(path)
    if not is_valid:
        print(f"[!] Path access denied: {error_msg}")
        return jsonify({
            "status": "error",
            "message": error_msg
        }), 403
    # =============================================

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

    # except Exception as e:
    #     return jsonify({
    #         "status": "error",
    #         "message": str(e)
    #     }), 500



@app.route("/send_files", methods=["POST"])
def send_files():
    data = request.get_json() or {}
    files = data.get("files", [])
    remote_host = data.get("remote_host")
    dest_dir = data.get("dest_dir")  # Destination directory on remote machine
    
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

    # ========== PATH RESTRICTION CHECK ==========
    # Validate all files are within the allowed root path
    for f in valid_files:
        is_valid, error_msg = validate_path_access(f)
        if not is_valid:
            print(f"[!] Send files access denied: {error_msg}")
            return jsonify({
                "status": "error",
                "message": error_msg
            }), 403
    # =============================================

    # Create task for tracking

    task_id = _create_transfer_task(valid_files, remote_host, "send")
    
    def _do_send_background():
        """Background thread to perform the actual transfer."""
        try:
            client_cert = env.get("CLIENT_CERT")
            client_key = env.get("CLIENT_KEY")
            ca_cert = env.get("CA_CERT") or env.get("ca_cert")

            print(f"[send_files] Starting background transfer to {remote_host}:{port}")
            print(f"[send_files] Files: {valid_files}")
            print(f"[send_files] dest_dir: {dest_dir}")
            print(f"[send_files] CA cert: {ca_cert}")
            print(f"[send_files] Client cert: {client_cert}")

            if not ca_cert:
                _complete_transfer_task(task_id, False, "CA_CERT not set")
                return

            async def _async_send():
                from sender_api_functions import send_file_with_progress
                
                print(f"[send_files] Connecting to QUIC {remote_host}:{port}...")
                conn = await quic_connect(
                    host=remote_host,
                    port=port,
                    insecure=False,
                    server_name=os.environ.get("SERVER_NAME"),
                    client_cert=client_cert,
                    client_key=client_key,
                    ca_cert=ca_cert,
                )
                print(f"[send_files] QUIC connection established!")
                try:
                    # Calculate total size for all files
                    total_size = sum(os.path.getsize(f) for f in valid_files)
                    bytes_sent_total = 0
                    
                    for path in valid_files:
                        print(f"[send_files] Sending file: {path}")
                        # Update current file in task
                        with _transfer_lock:
                            if task_id in _transfer_tasks:
                                _transfer_tasks[task_id]["current_file"] = path
                        
                        file_size = os.path.getsize(path)
                        
                        def on_progress(bytes_sent_file):
                            nonlocal bytes_sent_total
                            current_total = bytes_sent_total + bytes_sent_file
                            _update_transfer_progress(task_id, current_total, total_size)
                        
                        await send_file_with_progress(conn, path, on_progress, dest_dir=dest_dir)
                        bytes_sent_total += file_size
                        print(f"[send_files] File sent successfully: {path}")
                    
                    print(f"[send_files] All files sent, marking task complete")
                    _complete_transfer_task(task_id, True)
                finally:
                    await close_connection(conn)
                    print(f"[send_files] Connection closed")

            asyncio.run(_async_send())
            
        except Exception as e:
            import traceback
            error_msg = str(e) or f"{type(e).__name__}: (no message)"
            print(f"[send_files] Transfer error: {error_msg}")
            traceback.print_exc()
            _complete_transfer_task(task_id, False, error_msg)

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
    # First check if this is a fetch task that needs proxying to remote host
    fetch_info = None
    with _transfer_lock:
        if task_id in _fetch_task_mapping:
            fetch_info = _fetch_task_mapping[task_id].copy()
    
    # If it's a fetch task, proxy the status request to the remote host
    if fetch_info is not None:
        remote_host = fetch_info["remote_host"]
        remote_task_id = fetch_info["remote_task_id"]
        print(f"[transfer_status] Proxying status for task {task_id[:8]}... to {remote_host}")
        
        try:
            # Proxy the status request to the remote host
            proxy_url = f"http://{remote_host}:5000/transfer_status/{remote_task_id}"
            print(f"[transfer_status] GET {proxy_url}")
            resp = requests.get(proxy_url, timeout=5)
            
            if resp.status_code == 200:
                remote_status = resp.json()
                print(f"[transfer_status] Remote status: {remote_status.get('status')}, progress: {remote_status.get('progress')}")
                # Clean up mapping once transfer is complete or failed
                if remote_status.get("status") in ("completed", "failed"):
                    with _transfer_lock:
                        _fetch_task_mapping.pop(task_id, None)
                    print(f"[transfer_status] Task {task_id[:8]}... completed, removed from fetch mapping")
                return jsonify(remote_status), 200
            else:
                print(f"[transfer_status] Remote returned error: {resp.status_code} - {resp.text}")
                return jsonify({"status": "error", "message": f"Remote returned {resp.status_code}"}), resp.status_code
        except requests.exceptions.RequestException as e:
            print(f"[!] Failed to proxy transfer_status to {remote_host}: {e}")
            return jsonify({"status": "error", "message": f"Failed to contact remote host: {str(e)}"}), 502
    
    # Otherwise, check local tasks
    with _transfer_lock:
        if task_id not in _transfer_tasks:
            return jsonify({"status": "error", "message": "Task not found"}), 404
        
        task = _transfer_tasks[task_id].copy()
    
    # Recalculate progress based on elapsed time for in-progress tasks
    if task["status"] == "in_progress" and task.get("estimated_duration", 0) > 0:
        elapsed = time.time() - task["start_time"]
        task["progress"] = min(elapsed / task["estimated_duration"], 0.99)
    
    return jsonify({
        "status": task["status"],
        "progress": task["progress"],
        "total_size": task["total_size"],
        "transferred": task["transferred"],
        "files": task["files"],
        "current_file": task.get("current_file"),
        "error": task["error"],
        "estimated_duration": task.get("estimated_duration", 0),
        "elapsed": time.time() - task.get("start_time", time.time()),
    }), 200



@app.route("/receive_files", methods=["POST"])
def receive_files():
    # try:
    data = request.get_json() or {}
    remote_host = data.get("remote_host")
    files = data.get("files", [])
    dest_dir = data.get("dest_dir")  # Local directory where files should be saved
    
    if not remote_host:
        return jsonify({"status": "error", "message": "remote_host is required"}), 400
        
    if not isinstance(files, list) or not files:
        return jsonify({"status": "error", "message": "files must be a non-empty list"}), 400

    env = load_env_vars()
    our_host = env.get("host")
    
    if not our_host:
        return jsonify({"status": "error", "message": "Cannot determine local host IP"}), 500

    try:
        payload = {
            "remote_host": our_host,  
            "files": files            # Files on REMOTE system
        }
        # Pass destination directory if provided
        if dest_dir:
            payload["dest_dir"] = dest_dir
        
        response = requests.post(
            f"http://{remote_host}:5000/send_files",
            json=payload,
            timeout=60
        )
        
        # Accept both 200 and 202 (async) responses as success
        if response.status_code in (200, 202):
            result = response.json()
            
            # Register the remote task_id for proxying status requests
            remote_task_id = result.get("task_id")
            if remote_task_id:
                with _transfer_lock:
                    _fetch_task_mapping[remote_task_id] = {
                        "remote_host": remote_host,
                        "remote_task_id": remote_task_id
                    }
                print(f"[fetch] Registered task {remote_task_id[:8]}... for status proxying to {remote_host}")
            
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
    return flask_send_file(ca_path)


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



@app.route('/create_file', methods=['POST'])
def create_file():
    """Create a new empty file."""
    data = request.get_json() or {}
    path = data.get("path")
    if not path:
        return jsonify({"status": "error", "message": "path is required"}), 400

    remote_host = data.get("remote_host")
    if remote_host:
        env = load_env_vars()
        my_ip = env.get("host")
        if remote_host != my_ip and remote_host != "127.0.0.1" and remote_host != "localhost":
            try:
                resp = requests.post(f"http://{remote_host}:5000/create_file", json={"path": path}, timeout=10)
                return jsonify(resp.json()), resp.status_code
            except requests.exceptions.RequestException as e:
                return jsonify({"status": "error", "message": f"Failed to contact remote host: {str(e)}"}), 502

    path = os.path.normpath(path)
    is_valid, error_msg = validate_path_access(path)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403

    try:
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            return jsonify({"status": "error", "message": f"Parent directory does not exist: {parent}"}), 404
        with open(path, 'w') as f:
            pass  # Create empty file
        print(f"[create_file] Created: {path}")
        return jsonify({"status": "success", "path": path}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/create_folder', methods=['POST'])
def create_folder():
    """Create a new folder."""
    data = request.get_json() or {}
    path = data.get("path")
    if not path:
        return jsonify({"status": "error", "message": "path is required"}), 400

    remote_host = data.get("remote_host")
    if remote_host:
        env = load_env_vars()
        my_ip = env.get("host")
        if remote_host != my_ip and remote_host != "127.0.0.1" and remote_host != "localhost":
            try:
                resp = requests.post(f"http://{remote_host}:5000/create_folder", json={"path": path}, timeout=10)
                return jsonify(resp.json()), resp.status_code
            except requests.exceptions.RequestException as e:
                return jsonify({"status": "error", "message": f"Failed to contact remote host: {str(e)}"}), 502

    path = os.path.normpath(path)
    is_valid, error_msg = validate_path_access(path)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403

    try:
        os.makedirs(path, exist_ok=False)
        print(f"[create_folder] Created: {path}")
        return jsonify({"status": "success", "path": path}), 200
    except FileExistsError:
        return jsonify({"status": "error", "message": "Folder already exists"}), 409
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/delete_item', methods=['POST'])
def delete_item():
    """Delete a file or folder (recursive)."""
    import shutil
    data = request.get_json() or {}
    path = data.get("path")
    if not path:
        return jsonify({"status": "error", "message": "path is required"}), 400

    remote_host = data.get("remote_host")
    if remote_host:
        env = load_env_vars()
        my_ip = env.get("host")
        if remote_host != my_ip and remote_host != "127.0.0.1" and remote_host != "localhost":
            try:
                resp = requests.post(f"http://{remote_host}:5000/delete_item", json={"path": path}, timeout=10)
                return jsonify(resp.json()), resp.status_code
            except requests.exceptions.RequestException as e:
                return jsonify({"status": "error", "message": f"Failed to contact remote host: {str(e)}"}), 502

    path = os.path.normpath(path)
    is_valid, error_msg = validate_path_access(path)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403

    if not os.path.exists(path):
        return jsonify({"status": "error", "message": "Path does not exist"}), 404

    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
            print(f"[delete_item] Deleted folder: {path}")
        else:
            os.remove(path)
            print(f"[delete_item] Deleted file: {path}")
        return jsonify({"status": "success", "path": path}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/reset_environment', methods=['POST'])
def reset_environment_endpoint():
    """Reset certificates and .env configs, then restart the app."""
    try:
        from reset_env import reset_environment
        reset_environment()
        print("[reset] Environment reset complete. Scheduling app restart...")

        def _restart_app():
            """Restart the entire app after a brief delay."""
            time.sleep(1.5)  # Give time for the HTTP response to be sent
            app_dir = os.path.dirname(os.path.abspath(__file__))
            app_sh = os.path.join(app_dir, "app.sh")
            print(f"[reset] Restarting via: {app_sh}")
            os.execv("/bin/bash", ["/bin/bash", app_sh])

        restart_thread = threading.Thread(target=_restart_app, daemon=False)
        restart_thread.start()

        return jsonify({
            "status": "success",
            "message": "Environment reset. App will restart shortly."
        }), 200

    except Exception as e:
        print(f"[!] Reset error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    start_peer_discovery()
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        # use_reloader=False
    )
