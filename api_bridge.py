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
import asyncio  # NEW
from sender_api_functions import quic_connect, send_file, close_connection  # NEW


app = Flask(__name__)

CHUNK_SIZE = 64 * 1024
ENV_FILE = ".env"
CORS(app, resources={r"/*": {"origins":"*"}})




def check_subnet(ip):
    env = load_env_vars()
    host_ip = env["host"]
    if not host_ip:
        raise ValueError("HOST environment variable not set")

    ip_parts = ip.strip().split('.')
    default_parts = host_ip.strip().split('.')
    ed = ip_parts[-1]
    
    if ed == '1' or ed == "200" or ed == "255":
        return False
    
    return ip_parts[:-1] == default_parts[:-1]


def get_OS_TYPE(REMOTE_HOST=""):
    try:
        response = requests.post(f"http://{REMOTE_HOST}:5000/osinfo", 
                                json={"request": "osinfo"})
        if response.status_code == 200:
            data = response.json()
            return {"os": data.get("os", "linux"), "user": data.get("user")}
        else:
            return {"os": "linux", "user": None}
    except:
        return {"os": "linux", "user": None}

















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
    result = []
    
    print(host_list)
    for ip in host_list:
        subck = check_subnet(ip)
        print(subck)
        if subck:
            res = get_OS_TYPE(ip)
            username = res.get("user")
            result.append({"host": ip, "user": username, "os": res.get("os", "linux")})

    return jsonify(result)


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
        data = request.get_json()
        path = data.get("path")
        
        if not path:
            return jsonify({"status": "error", "message": "path is required"}), 400

        path = os.path.normpath(path)

        if not os.path.exists(path):
            return jsonify({"status": "error", "message": f"Path does not exist: {path}"}), 404

        if os.path.isfile(path):
            st = os.stat(path)
            info = {
                "name": os.path.basename(path),
                "path": path,
                "size": st.st_size,
                "mtime": datetime.utcfromtimestamp(st.st_mtime).isoformat() + "Z",
            }
            return jsonify({"status": "success", "type": "file", "info": info}), 200

        if os.path.isdir(path):
            try:
                items = sorted(os.listdir(path))
            except PermissionError:
                return jsonify({"status": "error", "message": "Permission denied"}), 403
            except Exception as e:
                return jsonify({"status": "error", "message": f"Listing failed: {str(e)}"}), 500

            return jsonify({"status": "success", "type": "directory", "files": items}), 200

        return jsonify({"status": "error", "message": f"Unknown filesystem object: {path}"}), 400

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



# ---------- NEW: trigger non-interactive QUIC send ----------
@app.route("/send_files", methods=["POST"])
def send_files():#ip=None):
    """
    Trigger a QUIC file send to a remote peer.

    JSON body:
    {
      "remote_host": "192.168.0.100",   # optional, uses DEST_HOST/HOST if missing
      "files": ["/abs/path/1", "/abs/path/2"]
    }
    """
    try:
        data = request.get_json() or {}
        files = data.get("files", [])
        remote_host = data.get("remote_host")
        # if ip:
        #     remote_host = ip
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

        async def _do_send():
            # For now we use insecure=True assuming self-signed
            conn = await quic_connect(host=remote_host, port=port, insecure=False)
            try:
                for path in valid_files:
                    await send_file(conn, path)
            finally:
                await close_connection(conn)

        asyncio.run(_do_send())

        return jsonify({
            "status": "success",
            "remote_host": remote_host,
            "port": port,
            "sent": valid_files,
            "missing": missing
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500




@app.route("/receive_files", methods=["POST"])
def receive_files():
    """
    Request files from a remote peer (pull operation).
    This tells the REMOTE peer to send files to US.
    
    JSON body:
    {
      "remote_host": "192.168.0.100",  # The peer that HAS the files
      "files": ["/remote/path/1"],      # File paths on REMOTE peer
      "local_dest": "/local/path"       # Not used, but kept for clarity
    }
    """
    try:
        data = request.get_json() or {}
        remote_host = data.get("remote_host")
        files = data.get("files", [])
        
        if not remote_host:
            return jsonify({"status": "error", "message": "remote_host is required"}), 400
            
        if not isinstance(files, list) or not files:
            return jsonify({"status": "error", "message": "files must be a non-empty list"}), 400

        # Get OUR IP address (where files should be sent)
        env = load_env_vars()
        our_host = env.get("host")
        
        if not our_host:
            return jsonify({"status": "error", "message": "Cannot determine local host IP"}), 500

        # Tell the REMOTE peer to send files to US
        # This is the key insight: we call the remote's /send_files endpoint
        # and pass OUR IP as the destination
        try:
            response = requests.post(
                f"http://{remote_host}:5000/send_files",
                json={
                    "remote_host": our_host,  # Send to US
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

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)