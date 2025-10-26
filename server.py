from flask import Flask, request, jsonify
import paramiko
import requests
import getpass
import platform
from mad import gethostlist
import json
import tkinter as tk
from tkinter import filedialog
import multiprocessing


app = Flask(__name__)

REMOTE_HOST = "192.168.0.104"
REMOTE_PASS = "1970"
REMOTE_BASE_DIR = "C:\\Users\\Muruga\\"  # Base directory (manual path, no os.path)
IS_REMOTE = True
ssh_client = None
HOST_FILE = "host_list.json"
OS_TYPE = ""
REMOTE_USER = ""



def join_path(base, name, os_type):
    """Safely join paths manually (no os.path)."""
    sep = "\\" if os_type == "windows" else "/"

    # If already absolute, just return as-is
    if os_type == "windows" and (":" in name or name.startswith("\\")):
        return name
    if os_type != "windows" and name.startswith("/"):
        return name

    base = base.rstrip("\\/")  
    return base + sep + name



# ---------- Get Remote OS Info ----------
def get_OS_TYPE(REMOTE_HOST=""):
    if not IS_REMOTE:
        return "windows" if platform.system().lower().startswith("win") else "linux"

    try:
        response = requests.post(f"http://{REMOTE_HOST}:5000/osinfo", json={"request": "osinfo"}, timeout=5)
        # print("Response from remote host:", response.status_code, response.text)
        if response.status_code == 200:
            data = response.json()
            return jsonify({"os": data.get("os", "linux"), "user": data.get("user")})
        else:
            return "linux"
    except Exception as e:
        print(f"Error contacting remote host: {e}")
        return "linux"


def init_ssh():
    global ssh_client
    if ssh_client is not None:
        try:
            ssh_client.close()
        except:
            pass
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(REMOTE_HOST, username=REMOTE_USER, password=REMOTE_PASS)
    return ssh_client


def run_remote_command(command):
    ssh = init_ssh()
    stdin, stdout, stderr = ssh.exec_command(command)
    output = stdout.read().decode()
    error = stderr.read().decode()
    exit_status = stdout.channel.recv_exit_status()
    return exit_status, output, error


def load_latest_host():
    """Load last used host credentials from host_list.json"""
    global REMOTE_HOST, REMOTE_USER, REMOTE_PASS, OS_TYPE


    try:
        with open(HOST_FILE, "r") as f:
            data = json.load(f)
        if not data:
            return False

        latest = data[-1]  # use last entry
        REMOTE_HOST = latest.get("ip")
        REMOTE_USER = latest.get("username")
        REMOTE_PASS = latest.get("password")
        OS_TYPE = latest.get("os_type", "linux")
        return True
    except Exception as e:
        print(f"Error reading host file: {e}")
        return False



@app.route("/selectdest", methods=["GET"])
def select_destination():
    try:
        root = tk.Tk()
        root.withdraw()
        folder = filedialog.askdirectory(title="Select Local Destination Folder")
        root.destroy()
        if not folder:
            return jsonify({"selected": None}), 200
        return jsonify({"selected": folder}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/lsithost", methods=["GET"])
def lsit_host():
    host_list = gethostlist()  # returns dict {hostname: ip}
    result = []

    for ip in host_list:
        print("Getting OS info for:", ip)
        res = get_OS_TYPE(ip)
        os_type = res.get_json().get("os")
        username = res.get_json().get("user")
        result.append({"host": ip, "os": os_type, "user": username})

    return jsonify(result)


@app.route("/connect", methods=["GET"])
def connect_host():
    if not load_latest_host():
        return jsonify({"error": "No saved host credentials"}), 400
    return jsonify({
        "host": REMOTE_HOST,
        "user": REMOTE_USER,
        "os": OS_TYPE
    })



@app.route("/osinfo", methods=["POST"])
def osinfo():
    try:
        os_name = platform.system().lower()
        user_name = getpass.getuser()
        print(f"OS Info Requested: OS={os_name}, User={user_name}")
        return jsonify({"os": os_name, "user": user_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- CREATE ----------
@app.route("/create", methods=["POST"])
def create_file():
    filename = request.json.get("filename")
    if not filename:
        return jsonify({"error": "filename required"}), 400

    full_path = join_path("", filename, OS_TYPE)

    if OS_TYPE == "windows":
        command = (
            f"powershell -Command "
            f"$f = New-Item -Path '{full_path}' -ItemType File -Force; "
            f"Write-Output ('Created file: ' + $f.FullName)"
        )
    else:
        command = f'touch "{full_path}" && echo Created file: {full_path}'

    status, out, err = run_remote_command(command)
    return jsonify({"status": status, "output": out, "error": err})


# ---------- DELETE ----------
@app.route("/delete", methods=["DELETE"])
def delete_file():
    filename = request.json.get("filename")
    if not filename:
        return jsonify({"error": "filename required"}), 400

    full_path = join_path("", filename, OS_TYPE)

    if OS_TYPE == "windows":
        command = (
            f"powershell -Command "
            f"Remove-Item -Path '{full_path}' -Force -ErrorAction SilentlyContinue; "
            f"Write-Output 'Deleted file: {full_path}'"
        )
    else:
        command = f'rm -f "{full_path}" && echo "Deleted file: {full_path}"'
    print("comm", command)
    status, out, err = run_remote_command(command)
    return jsonify({"status": status, "output": out, "error": err})


# ---------- COPY ----------
@app.route("/copy", methods=["POST"])
def copy_file():
    source = request.json.get("source")
    destination = request.json.get("destination")
    if not source or not destination:
        return jsonify({"error": "source and destination required"}), 400

    if OS_TYPE == "windows":
        command = (
            f"powershell -Command "
            f"Copy-Item -Path '{source}' -Destination '{destination}' -Force -ErrorAction SilentlyContinue; "
            f"Write-Output 'Copied file: {source} → {destination}'"
        )
    else:
        command = f'cp -f "{source}" "{destination}" && echo "Copied file: {source} → {destination}"'

    status, out, err = run_remote_command(command)
    return jsonify({"status": status, "output": out, "error": err})


# ---------- MOVE ----------
@app.route("/move", methods=["POST"])
def move_file():
    source = request.json.get("source")
    destination = request.json.get("destination")
    if not source or not destination:
        return jsonify({"error": "source and destination required"}), 400

    if OS_TYPE == "windows":
        command = (
            f"powershell -Command "
            f"Move-Item -Path '{source}' -Destination '{destination}' -Force -ErrorAction SilentlyContinue; "
            f"Write-Output 'Moved file: {source} → {destination}'"
        )
    else:
        command = f'mv -f "{source}" "{destination}" && echo "Moved file: {source} → {destination}"'

    status, out, err = run_remote_command(command)
    return jsonify({"status": status, "output": out, "error": err})


if __name__ == "__main__":
    app.run(host="0.0.0.0")
