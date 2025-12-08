#api_bridge.py
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


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)