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
import time
import subprocess

# CRITICAL: Set up paths FIRST, before importing any local modules
APP_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(APP_DIR))

# Now import local modules - using AppConfig for centralized configuration
from app_config import get_config, AppConfig
from startsetup import load_env_vars  # Keep for backward compatibility
from scanner import gethostlist
from quic_cli import send_file_cli, start_receiver_cli
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

CHUNK_SIZE = 64 * 1024  # Default; overridden at runtime by _get_dynamic_chunk_size()
ENV_FILE = ".env"
# CORS(app, resources={r"/*": {"origins":"*"}})

# Transfer task registry for progress tracking
import uuid
import time
from threading import Lock
from wifi_speed import estimate_transfer_time_seconds, get_wifi_speed, calculate_optimal_chunk_size

# Registry of active receiver subprocesses: port -> Popen
# Used by /prepare_receive to prevent port collisions.
_active_receivers: dict = {}
_receiver_lock = Lock()

# ==================== PATH RESTRICTION HELPERS ====================
# Path security functions imported from path_security module
# get_lanfxplorer_root(), validate_path_access(), is_path_within_root(),
# is_path_at_minimum_depth() are all imported at the top of this file.

def get_root_path():
    """Get the configured root path - uses Lanfxplorer directory."""
    return get_lanfxplorer_root()

# ==================================================================


def get_time():
    def decorator(func):
        from functools import wraps
        import time
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            result = func(*args, **kwargs)
            duration = time.time() - start
            print(f"[get_time] {func.__name__} took {duration:.4f} seconds")
            return result
        return wrapper
    return decorator

# ── Transfer task registry (lightweight: status + file counts only) ───────────
# task_id -> {status, total_files, completed_count, failed_count, start_time}
# Re-enabled with push-driven updates from /file_received.
_transfer_tasks = {}
_transfer_lock  = Lock()

# ── Job-event registry: job_id -> sender_ip ───────────────────────────────────
# Populated by /prepare_receive; used by _watch_receiver to know where to push.
# job_id is a per-file UUID distinct from task_id (which spans all files).
_job_sender_map: dict = {}    # job_id -> sender_ip
_job_map_lock   = Lock()

# ── Fetch-task mapping (kept for completeness; push makes it rarely needed) ───
_fetch_task_mapping = {}

# Cache WiFi speed (detect once at startup or first transfer)
_wifi_speed_mbps = None

def _get_cached_wifi_speed():
    """Get cached WiFi speed or detect it."""
    global _wifi_speed_mbps, CHUNK_SIZE
    if _wifi_speed_mbps is None:
        _wifi_speed_mbps = get_wifi_speed()
        if _wifi_speed_mbps:
            print(f"[wifi_speed] Detected: {_wifi_speed_mbps} Mbps")
        else:
            print("[wifi_speed] Could not detect, using fallback 100 Mbps")
            _wifi_speed_mbps = 100  # Fallback
        CHUNK_SIZE = calculate_optimal_chunk_size(_wifi_speed_mbps)
        print(f"[wifi_speed] Dynamic chunk size: {CHUNK_SIZE // 1024} KB")
    return _wifi_speed_mbps


def _create_transfer_task(files: list, remote_host: str, direction: str = "send") -> str:
    """Create a lightweight transfer task entry and return its ID.

    Tracks only: status, total_files, completed_count, failed_count.
    No byte-level tracking — UI uses indeterminate bar while in_progress.
    """
    task_id = str(uuid.uuid4())
    with _transfer_lock:
        _transfer_tasks[task_id] = {
            "status":          "in_progress",
            "total_files":     len(files),
            "completed_count": 0,
            "failed_count":    0,
            "start_time":      time.time(),
            "error":           None,
        }
    print(f"[transfer] Task {task_id[:8]}... created: {len(files)} file(s) → {remote_host}")
    return task_id


def _update_transfer_progress(task_id: str, bytes_sent: int, total_bytes: int):
    """No-op — byte-level progress is not tracked; UI uses indeterminate bar."""
    pass


def _complete_transfer_task(task_id: str, success: bool, error: str = None):
    """Mark a transfer task as completed or failed."""
    with _transfer_lock:
        if task_id in _transfer_tasks:
            _transfer_tasks[task_id]["status"] = "completed" if success else "failed"
            _transfer_tasks[task_id]["error"]  = error
            elapsed = time.time() - _transfer_tasks[task_id]["start_time"]
            print(f"[transfer] Task {task_id[:8]}... "
                  f"{'completed' if success else 'FAILED'} in {elapsed:.1f}s")


def _mark_file_done(task_id: str, filename: str, success: bool) -> None:
    """Record one file as done within a multi-file task.

    Called by the sender loop after each send_file_cli() returns.
    When completed_count + failed_count == total_files the task auto-completes.
    """
    with _transfer_lock:
        if task_id not in _transfer_tasks:
            return
        task = _transfer_tasks[task_id]
        if success:
            task["completed_count"] += 1
        else:
            task["failed_count"] += 1
        done = task["completed_count"] + task["failed_count"]
        if done >= task["total_files"]:
            if task["failed_count"] == 0:
                task["status"] = "completed"
            elif task["completed_count"] == 0:
                task["status"] = "failed"
                task["error"]  = f"All {task['failed_count']} file(s) failed"
            else:
                task["status"] = "completed"   # partial — treat as done for UI
                task["error"]  = (
                    f"Partial: {task['completed_count']} sent, "
                    f"{task['failed_count']} failed"
                )


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

    if os.path.isdir(path):
        recursive = data.get("recursive", False)
        files = []

        if recursive:
            # ── Recursive walk: flat list of every file in the entire subtree ──
            # Useful for the UI to verify all expected files arrived after a
            # folder transfer (compare expected relpaths vs returned relpaths).
            try:
                for dirpath, dirnames, filenames in os.walk(path):
                    # Skip hidden dirs to avoid permission noise
                    dirnames[:] = [d for d in sorted(dirnames) if not d.startswith('.')]
                    for fname in sorted(filenames):
                        full_path = os.path.join(dirpath, fname)
                        try:
                            st = os.stat(full_path)
                            rel = os.path.relpath(full_path, path)
                            files.append({
                                "name":         fname,
                                "path":         full_path,
                                "rel_path":     rel,
                                "is_directory": False,
                                "size":         st.st_size,
                                "mtime":        datetime.utcfromtimestamp(
                                                    st.st_mtime).isoformat() + "Z",
                            })
                        except (PermissionError, FileNotFoundError):
                            continue
            except PermissionError:
                return jsonify({"status": "error", "message": "Permission denied"}), 403

            return jsonify({
                "status":    "success",
                "type":      "directory",
                "recursive": True,
                "files":     files,
            }), 200

        # ── Non-recursive (original behaviour) ──
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
                    "name":         name,
                    "path":         full_path,
                    "is_directory": is_dir,
                    "size":         None if is_dir else st.st_size,
                    "mtime":        datetime.utcfromtimestamp(
                                        st.st_mtime).isoformat() + "Z",
                })
            except PermissionError:
                continue
            except FileNotFoundError:
                continue

        return jsonify({
            "status": "success",
            "type":   "directory",
            "files":  files,
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
@get_time()
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

    # verify files exist and expand directories
    # Phase 1: Build tree structure — walk directories recursively
    valid_files = []        # Regular files (abs_path only)
    folder_file_map = []    # Folder contents: list of (abs_path, rel_path) tuples
    missing = []
    for f in files:
        if os.path.isfile(f):
            valid_files.append(f)
        elif os.path.isdir(f):
            # Walk directory recursively and collect all files
            folder_name = os.path.basename(f)
            parent_dir = os.path.dirname(f)
            print(f"[send_files] Walking directory: {f} (folder_name={folder_name})")
            for dirpath, dirnames, filenames in os.walk(f):
                for fname in filenames:
                    abs_file = os.path.join(dirpath, fname)
                    # Preserve path relative to parent of the selected folder
                    # e.g. /home/user/Lanfxplorer/myfolder/sub/file.txt
                    #   -> myfolder/sub/file.txt
                    rel_file = os.path.relpath(abs_file, parent_dir)
                    folder_file_map.append((abs_file, rel_file))
            print(f"[send_files] Directory {folder_name}: found {len([m for m in folder_file_map if m[1].startswith(folder_name)])} files")
        else:
            missing.append(f)

    if not valid_files and not folder_file_map:
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
    for abs_path, rel_path in folder_file_map:
        is_valid, error_msg = validate_path_access(abs_path)
        if not is_valid:
            print(f"[!] Send files access denied (folder content): {error_msg}")
            return jsonify({
                "status": "error",
                "message": error_msg
            }), 403
    # =============================================

    # Build combined file list for task tracking
    all_file_paths = valid_files + [abs_p for abs_p, _ in folder_file_map]

    # [TRANSFER STATUS DISABLED] task creation commented out
    # task_id = _create_transfer_task(all_file_paths, remote_host, "send")
    task_id = str(uuid.uuid4())  # Stub task_id — status tracking is disabled
    
    def _do_send_background():
        """
        Background thread: coordinate with remote /prepare_receive, then invoke
        the MsQuic sender binary once per file via quic_cli.send_file_cli().

        Error strategy
        ──────────────
        • Transport error (can't reach /prepare_receive) → abort entire task.
        • File-level error (503 busy, bad CLI exit, exception) → mark that file
          as failed, continue with the remaining files.  This prevents a single
          bad file from locking up the whole folder transfer.
        """
        try:
            print(f"[send_files] Starting background transfer to {remote_host}:{port}")
            print(f"[send_files] Regular files: {valid_files}")
            print(f"[send_files] Folder files: {len(folder_file_map)} files from directories")
            print(f"[send_files] dest_dir: {dest_dir}")

            all_files = (
                [(f, None) for f in valid_files] +
                [(abs_p, rel_p) for abs_p, rel_p in folder_file_map]
            )

            total_size      = sum(os.path.getsize(f) for f, _ in all_files if os.path.isfile(f))
            bytes_sent_total = 0
            transport_error  = None   # set to error string on unrecoverable network failure

            for file_path, rel_path in all_files:
                filename  = rel_path if rel_path else os.path.basename(file_path)
                file_size = os.path.getsize(file_path)

                with _transfer_lock:
                    if task_id in _transfer_tasks:
                        _transfer_tasks[task_id]["current_file"] = file_path

                print(f"[send_files] [{time.asctime()}] Preparing remote receiver for: {filename}")

                # ── Step 1: Ask remote peer to start its receiver ──────────────
                try:
                    prep_resp = requests.post(
                        f"http://{remote_host}:5000/prepare_receive",
                        json={
                            "filename": filename,
                            "filesize": file_size,
                            "dest_dir": dest_dir,
                            "task_id":  task_id,   # for push-back /file_received
                        },
                        timeout=20,
                    )

                except requests.RequestException as e:
                    # Can't reach the remote at all — abort entire transfer.
                    transport_error = f"Cannot reach /prepare_receive on {remote_host}: {e}"
                    print(f"[send_files] TRANSPORT ERROR: {transport_error}")
                    break

                if prep_resp.status_code == 503:
                    # Remote busy — this file fails, try next.
                    print(f"[send_files] Remote busy for '{filename}' (503) — skipping")
                    _mark_file_done(task_id, filename, False)
                    continue

                if prep_resp.status_code != 200:
                    print(f"[send_files] prepare_receive error {prep_resp.status_code} "
                          f"for '{filename}' — skipping. Response: {prep_resp.text[:120]}")
                    _mark_file_done(task_id, filename, False)
                    continue

                prep_info = prep_resp.json()
                quic_port = int(prep_info.get("receiver_port", port))

                print(
                    f"[send_files] Remote receiver ready on port {quic_port} "
                    f"→ {prep_info.get('save_path', '?')}"
                )

                # ── Step 2: Wait for remote receiver to bind ───────────────────
                # Minimum grace period for the receiver process to open its UDP port.
                time.sleep(0.3)

                # ── Step 3: Invoke MsQuic sender binary ────────────────────────
                print(f"[send_files] [{time.asctime()}] Invoking sender binary for: {file_path}")
                try:
                    ok = send_file_cli(
                        file_path,
                        remote_host=remote_host,
                        remote_port=quic_port,
                    )
                except Exception as exc:
                    print(f"[send_files] Exception sending '{filename}': {exc}")
                    ok = False

                _mark_file_done(task_id, filename, ok)

                if ok:
                    bytes_sent_total += file_size
                    _update_transfer_progress(task_id, bytes_sent_total, total_size)
                    print(f"[send_files] [{time.asctime()}] ✓ Sent: {filename}")
                else:
                    print(f"[send_files] [{time.asctime()}] ✗ Failed: {filename}")

                # ── Step 4: Wait for remote port to fully release ──────────────
                # TEMPORARILY DISABLED — proceeding immediately to next file.
                # Re-enable if 503 "port busy" collisions reappear on folder transfers.
                # _port_free = False
                # _port_deadline = time.time() + 8
                # while time.time() < _port_deadline:
                #     try:
                #         _probe = requests.post(
                #             f"http://{remote_host}:5000/prepare_receive",
                #             json={"filename": "__port_probe__",
                #                   "filesize": 0, "probe": True},
                #             timeout=3,
                #         )
                #         if _probe.status_code != 503:
                #             _port_free = True
                #             break
                #     except requests.RequestException:
                #         _port_free = True
                #         break
                #     time.sleep(0.4)
                # if not _port_free:
                #     print(f"[send_files] Port still busy after 8s — continuing anyway")

            # ── After the loop: decide overall task outcome ────────────────────
            if transport_error:
                _complete_transfer_task(task_id, False, transport_error)
            else:
                with _transfer_lock:
                    task_snap = _transfer_tasks.get(task_id, {})
                failed = task_snap.get("failed_files", [])
                done   = task_snap.get("completed_files", [])

                if not done and failed:
                    # Every file failed
                    _complete_transfer_task(
                        task_id, False,
                        f"All {len(failed)} file(s) failed: {', '.join(failed[:3])}"
                        + (" ..." if len(failed) > 3 else "")
                    )
                elif failed:
                    # Partial success
                    _complete_transfer_task(
                        task_id, True,
                        f"Partial: {len(done)} sent, {len(failed)} failed: "
                        + ", ".join(failed[:3]) + (" ..." if len(failed) > 3 else "")
                    )
                else:
                    print(f"[send_files] All {len(done)} file(s) sent successfully.")
                    _complete_transfer_task(task_id, True)

        except Exception as e:
            import traceback
            error_msg = str(e) or f"{type(e).__name__}: (no message)"
            print(f"[send_files] Unexpected transfer error: {error_msg}")
            traceback.print_exc()
            _complete_transfer_task(task_id, False, error_msg)


    # Start transfer in background thread
    thread = threading.Thread(target=_do_send_background, daemon=True)
    thread.start()

    # Return immediately with task_id so Flutter can poll /transfer_status
    return jsonify({
        "status":      "in_progress",
        "task_id":     task_id,
        "remote_host": remote_host,
        "port":        port,
        "files":       all_file_paths,
        "missing":     missing
    }), 202  # 202 Accepted


# ── /transfer_status ───────────────────────────────────────────────────────────────────
@app.route("/transfer_status/<task_id>", methods=["GET"])
def transfer_status(task_id):
    """Return lightweight transfer status (push-driven via /file_received).

    Response fields intentionally minimal — UI only needs status + counts.
    """
    with _transfer_lock:
        if task_id not in _transfer_tasks:
            # Unknown task — return completed so the UI stops polling
            return jsonify({
                "status":          "completed",
                "total_files":     0,
                "completed_count": 0,
                "failed_count":    0,
                "error":           None,
                "elapsed":         0,
            }), 200
        task = _transfer_tasks[task_id].copy()

    return jsonify({
        "status":          task["status"],
        "total_files":     task["total_files"],
        "completed_count": task["completed_count"],
        "failed_count":    task["failed_count"],
        "error":           task["error"],
        "elapsed":         time.time() - task["start_time"],
        # Legacy fields — kept so old Flutter code doesn’t throw on missing keys
        "progress":        (
            task["completed_count"] / max(task["total_files"], 1)
        ),
        "total_size":      0,
        "transferred":     0,
        "files":           [],
        "current_file":    None,
        "estimated_duration": 0,
        "completed_files": [],
        "failed_files":    [],
    }), 200


# ── /file_received — receiver-push UI notification endpoint ───────────────────
# Called ONLY by the remote receiver-watcher thread (via best-effort daemon
# thread) when a file is received cleanly.  Purely a UI counter update.
# Does NOT affect transfer flow, binary lifecycle, or port management.
@app.route("/file_received", methods=["POST"])
def file_received():
    """Receive a push notification from the remote receiver when a file completes.

    Payload:  { "task_id": str, "filename": str, "success": bool }
    Response: 200 always (fire-and-forget; errors are silently swallowed by caller)
    """
    data     = request.get_json(silent=True) or {}
    task_id  = data.get("task_id",  "")
    filename = data.get("filename", "?")
    success  = bool(data.get("success", True))

    if not task_id:
        return jsonify({"ok": False, "reason": "task_id required"}), 400

    with _transfer_lock:
        if task_id not in _transfer_tasks:
            # Task may have already been cleaned up — ignore silently
            print(f"[file_received] Unknown task_id {task_id[:8]}... (ignored)")
            return jsonify({"ok": True, "note": "task not found, ignored"}), 200

        task = _transfer_tasks[task_id]
        if success:
            task["completed_count"] += 1
        else:
            task["failed_count"] += 1

        done = task["completed_count"] + task["failed_count"]
        if done >= task["total_files"]:
            if task["failed_count"] == 0:
                task["status"] = "completed"
            elif task["completed_count"] == 0:
                task["status"] = "failed"
                task["error"]  = f"All {task['failed_count']} file(s) failed on receiver"
            else:
                task["status"] = "completed"
                task["error"]  = (
                    f"Partial: {task['completed_count']} received, "
                    f"{task['failed_count']} failed"
                )

    status_now = _transfer_tasks[task_id]["status"]
    print(
        f"[file_received] task={task_id[:8]}  file='{filename}'  "
        f"ok={success}  task_status={status_now}"
    )
    return jsonify({"ok": True}), 200
# @app.route("/transfer_status/<task_id>", methods=["GET"])
# def transfer_status(task_id):
#     """Get the status of a transfer task."""
#     # First check if this is a fetch task that needs proxying to remote host
#     fetch_info = None
#     with _transfer_lock:
#         if task_id in _fetch_task_mapping:
#             fetch_info = _fetch_task_mapping[task_id].copy()
#
#     # If it's a fetch task, proxy the status request to the remote host
#     if fetch_info is not None:
#         remote_host = fetch_info["remote_host"]
#         remote_task_id = fetch_info["remote_task_id"]
#
#         try:
#             proxy_url = f"http://{remote_host}:5000/transfer_status/{remote_task_id}"
#             resp = requests.get(proxy_url, timeout=5)
#
#             if resp.status_code == 200:
#                 remote_status = resp.json()
#                 # Clean up mapping once transfer is complete or failed —
#                 # this stops future proxy calls immediately.
#                 if remote_status.get("status") in ("completed", "failed"):
#                     with _transfer_lock:
#                         _fetch_task_mapping.pop(task_id, None)
#                     print(
#                         f"[transfer_status] Task {task_id[:8]}... "
#                         f"{remote_status['status']}, fetch mapping removed"
#                     )
#                 return jsonify(remote_status), 200
#             else:
#                 return jsonify({
#                     "status": "error",
#                     "message": f"Remote returned {resp.status_code}"
#                 }), resp.status_code
#         except requests.exceptions.RequestException as e:
#             print(f"[!] Failed to proxy transfer_status to {remote_host}: {e}")
#             return jsonify({
#                 "status": "error",
#                 "message": f"Failed to contact remote host: {str(e)}"
#             }), 502
#
#     # ── Local task ───────────────────────────────────────────────────────────
#     with _transfer_lock:
#         if task_id not in _transfer_tasks:
#             return jsonify({"status": "error", "message": "Task not found"}), 404
#         task = _transfer_tasks[task_id].copy()
#
#     # ── Failsafe: if the sender thread already marked this completed or failed,
#     # return immediately — do NOT recalculate anything from time estimates.
#     if task["status"] in ("completed", "failed"):
#         return jsonify({
#             "status":           task["status"],
#             "progress":         task["progress"],
#             "total_size":       task["total_size"],
#             "transferred":      task["transferred"],
#             "files":            task["files"],
#             "current_file":     task.get("current_file"),
#             "error":            task["error"],
#             "estimated_duration": task.get("estimated_duration", 0),
#             "elapsed":          time.time() - task.get("start_time", time.time()),
#             # ── Per-file tracking ──
#             "total_files":      task.get("total_files", len(task["files"])),
#             "completed_count":  task.get("completed_count", 0),
#             "completed_files":  task.get("completed_files", []),
#             "failed_files":     task.get("failed_files", []),
#         }), 200
#
#     # ── In-progress ─────────────────────────────────────────────────────────
#     return jsonify({
#         "status":           task["status"],
#         "progress":         task["progress"],
#         "total_size":       task["total_size"],
#         "transferred":      task["transferred"],
#         "files":            task["files"],
#         "current_file":     task.get("current_file"),
#         "error":            task["error"],
#         "estimated_duration": task.get("estimated_duration", 0),
#         "elapsed":          time.time() - task.get("start_time", time.time()),
#         # ── Per-file tracking (live-updated by _mark_file_done) ──
#         "total_files":      task.get("total_files", len(task["files"])),
#         "completed_count":  task.get("completed_count", 0),
#         "completed_files":  task.get("completed_files", []),
#         "failed_files":     task.get("failed_files", []),
#     }), 200
# ─────────────────────────────────────────────────────────────────────────────




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
            
            # [TRANSFER STATUS DISABLED] task mapping for status proxying commented out
            # remote_task_id = result.get("task_id")
            # if remote_task_id:
            #     with _transfer_lock:
            #         _fetch_task_mapping[remote_task_id] = {
            #             "remote_host": remote_host,
            #             "remote_task_id": remote_task_id
            #         }
            #     print(f"[fetch] Registered task {remote_task_id[:8]}... for status proxying to {remote_host}")
            
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
    """
    Authenticate with a remote peer over TCP (port 4437, HandshakeService).

    Flow
    ----
    1. Sender opens a TCP socket to dest_host:4437.
    2. Sends: { "type": "AUTH", "password": "...", "fp": "<cert fp>" }
    3. Receiver's HandshakeService thread verifies password via keyring.
    4. Returns: { "status": "AUTH_OK" } or { "status": "AUTH_FAIL", ... }

    No QUIC / UDP is involved in the handshake process.
    """
    try:
        data = request.get_json() or {}
        dest_host = data.get('dest_host')
        password = data.get('password')

        if not dest_host:
            return jsonify({'success': False, 'error': 'dest_host is required'}), 400

        if not password:
            return jsonify({'success': False, 'error': 'password is required'}), 400

        env = load_env_vars()
        client_cert = env.get('certi') or 'cert.pem'
        client_key  = env.get('key')   or 'key.pem'
        ca_cert     = env.get('ca_cert') or 'ca_cert.pem'

        if not os.path.isfile(client_cert):
            return jsonify({'success': False, 'error': f'Client certificate not found: {client_cert}'}), 500

        if not os.path.isfile(ca_cert):
            return jsonify({'success': False, 'error': f'CA certificate not found: {ca_cert}'}), 500

        # ── Pure TCP handshake (port 4437, HandshakeService) ──────────────────────
        # No QUIC involved. tcp_handshake() opens a plain TCP socket,
        # sends the password, reads AUTH_OK / AUTH_FAIL, then closes it.
        from pki.handshake import tcp_handshake

        async def _do_tcp_auth():
            return await tcp_handshake(
                dest_host=dest_host,
                password=password,
                client_cert=client_cert,
                client_key=client_key,
                ca_cert=ca_cert,
            )

        print(f"[handshake] Initiating TCP AUTH with {dest_host}:4437...")
        success = asyncio.run(_do_tcp_auth())

        if success:
            print(f"[handshake] ✓ AUTH_OK from {dest_host}")
            return jsonify({'success': True}), 200
        else:
            print(f"[handshake] ✗ AUTH_FAIL from {dest_host}")
            return jsonify({
                'success': False,
                'error': 'Authentication failed. Check password or peer availability.'
            }), 401

    except Exception as e:
        print(f"[!] Handshake error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/check_password', methods=['GET'])
def check_password():
    """Check if a password is configured in the keyring."""
    try:
        from config_manager import has_password
        return jsonify({"has_password": has_password()}), 200
    except Exception as e:
        return jsonify({"has_password": False, "error": str(e)}), 200


@app.route('/set_password', methods=['POST'])
def set_password_endpoint():
    """Store a password in the OS keyring."""
    data = request.get_json()
    password = data.get('password', '')
    if not password:
        return jsonify({"error": "Password is required"}), 400
    try:
        from config_manager import set_password
        success = set_password(password)
        return jsonify({"success": success}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


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


@app.route('/fix_firewall', methods=['POST'])
def fix_firewall():
    """Run firewall_manager.py --install with elevated privileges."""
    try:
        import shutil
        app_dir = os.path.dirname(os.path.abspath(__file__))
        fw_script = os.path.join(app_dir, "firewall_manager.py")

        if not os.path.isfile(fw_script):
            return jsonify({
                "success": False,
                "error": "firewall_manager.py not found"
            }), 500

        system = platform.system().lower()

        if system == "windows":
            # On Windows, use runas for elevation (non-interactive)
            cmd = [sys.executable, fw_script, "--install"]
        else:
            # On Linux/macOS, use pkexec (polkit) for GUI privilege prompt
            # Falls back to sudo if pkexec is not available
            if shutil.which("pkexec"):
                cmd = ["pkexec", sys.executable, fw_script, "--install"]
            else:
                cmd = ["sudo", sys.executable, fw_script, "--install"]

        print(f"[fix_firewall] Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = (result.stdout or "") + (result.stderr or "")
        success = result.returncode == 0

        print(f"[fix_firewall] Exit code: {result.returncode}")
        if output.strip():
            print(f"[fix_firewall] Output: {output.strip()[:500]}")

        return jsonify({
            "success": success,
            "output": output.strip(),
            "returncode": result.returncode,
        }), 200

    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "error": "Firewall fix timed out (30s). You may need to run manually: sudo python3 firewall_manager.py --install"
        }), 504
    except Exception as e:
        print(f"[!] fix_firewall error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# /prepare_receive — Phase 2: receiver-side coordination endpoint
# ---------------------------------------------------------------------------

@app.route("/prepare_receive", methods=["POST"])
def prepare_receive():
    """
    Called by the sending peer (via send_files/_do_send_background) before
    invoking the MsQuic sender binary.  This endpoint:
      1. Validates and computes the absolute save path from filename + dest_dir.
      2. Checks the QUIC port is free (no active receiver).
      3. Spawns c_ver/receiver as a background subprocess writing to that path.
      4. Returns the port and resolved save_path so the sender knows where to connect.

    Request body:
        { "filename": "foo.tar.gz",
          "filesize": 1234567,
          "dest_dir": "/optional/override/path"  }   # dest_dir may be null

    Response:
        200  { "status": "ready", "receiver_port": 4433, "save_path": "/abs/path" }
        400  bad request
        403  path security violation
        503  QUIC port already in use by an active transfer
        500  internal error
    """
    data         = request.get_json(silent=True) or {}
    filename_raw = data.get("filename", "").strip()
    filesize     = int(data.get("filesize", 0))
    dest_dir_raw = data.get("dest_dir") or None

    if not filename_raw:
        return jsonify({"status": "error", "message": "filename is required"}), 400

    # ── Sanitise filename (mirrors receiver_api_functions logic) ──────────────
    filename = filename_raw.lstrip("/")
    parts    = filename.replace("\\", "/").split("/")
    safe_parts = [p for p in parts if p and p != ".."]
    filename = "/".join(safe_parts) if safe_parts else "unnamed_file"

    # ── Resolve destination directory ─────────────────────────────────────────
    if dest_dir_raw:
        is_valid, error_msg = validate_path_access(dest_dir_raw)
        if not is_valid:
            print(f"[prepare_receive] SECURITY: Rejected dest_dir: {error_msg}")
            return jsonify({"status": "error", "message": error_msg}), 403
        base_dir = dest_dir_raw.replace("\\", "/").rstrip("/")
    else:
        base_dir = get_lanfxplorer_root()

    is_valid, error_msg = validate_path_access(base_dir)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403

    os.makedirs(base_dir, exist_ok=True)

    save_path = os.path.normpath(os.path.abspath(os.path.join(base_dir, filename)))
    is_valid, error_msg = validate_path_access(save_path)
    if not is_valid:
        return jsonify({"status": "error", "message": error_msg}), 403

    parent = os.path.dirname(save_path)
    os.makedirs(parent, exist_ok=True)

    # ── Probe-only mode ───────────────────────────────────────────────────────
    # When probe=True the caller just wants to know if the port is free.
    # Returns 200 (free) or 503 (busy) without spawning any subprocess.
    is_probe = bool(data.get("probe", False))

    # ── Port availability check + optional receiver spawn (atomic under lock) ──
    from app_config import get_config, AppConfig
    config    = get_config()
    quic_port = config.port or AppConfig.QUIC_PORT

    spawned_proc = None
    with _receiver_lock:
        # Clean up any receiver processes that have already exited
        for p in list(_active_receivers.keys()):
            if _active_receivers[p].poll() is not None:
                _active_receivers.pop(p, None)

        if quic_port in _active_receivers:
            # Port still held by a live receiver
            return jsonify({
                "status": "error",
                "message": f"QUIC port {quic_port} is already in use. Retry shortly."
            }), 503

        if is_probe:
            # Probe only — port is free, no need to spawn
            return jsonify({"status": "free", "receiver_port": quic_port}), 200

        # ── Spawn c_ver/receiver subprocess ──────────────────────────────────
        print(
            f"[prepare_receive] Starting receiver for '{filename}' "
            f"({filesize} bytes) → {save_path}"
        )
        try:
            spawned_proc = start_receiver_cli(save_path=save_path, port=quic_port)
        except Exception as e:
            print(f"[prepare_receive] Failed to start receiver: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500

        _active_receivers[quic_port] = spawned_proc

    # Generate a per-file job_id for the push notification side-channel
    job_id    = str(uuid.uuid4())
    sender_ip = request.remote_addr  # IP of the machine that sent the QUIC data
    task_id_hint = data.get("task_id", "")  # optional hint from sender

    with _job_map_lock:
        _job_sender_map[job_id] = {
            "sender_ip":  sender_ip,
            "task_id":    task_id_hint,
            "filename":   filename,
        }

    # Spawn a watcher thread that:
    #   1. Removes the port entry once the receiver exits (original purpose)
    #   2. Fires a best-effort push notification back to the sender (UI only)
    def _watch_receiver(p, proc, jid, s_ip, t_id, fname):
        proc.wait()
        success = (proc.returncode == 0)

        # ── Original: release port ────────────────────────────────────────────
        with _receiver_lock:
            _active_receivers.pop(p, None)
        print(
            f"[prepare_receive] Receiver on port {p} exited "
            f"(returncode={proc.returncode})"
        )

        # ── NEW: push UI notification to sender (fire-and-forget) ────────────
        # Runs in its own daemon thread so it can never block the watcher.
        def _push_notification():
            if not s_ip or not t_id:
                return
            try:
                requests.post(
                    f"http://{s_ip}:5000/file_received",
                    json={
                        "task_id":  t_id,
                        "filename": fname,
                        "success":  success,
                    },
                    timeout=3,
                )
                print(
                    f"[push] → {s_ip}/file_received  task={t_id[:8]}  "
                    f"file='{fname}'  ok={success}"
                )
            except Exception as e:
                # Best-effort only — never propagate
                print(f"[push] /file_received notification failed (non-fatal): {e}")
            finally:
                with _job_map_lock:
                    _job_sender_map.pop(jid, None)

        threading.Thread(target=_push_notification, daemon=True).start()

    threading.Thread(
        target=_watch_receiver,
        args=(quic_port, spawned_proc, job_id, sender_ip, task_id_hint, filename),
        daemon=True,
    ).start()

    return jsonify({
        "status":        "ready",
        "receiver_port": quic_port,
        "save_path":     save_path,
        "job_id":        job_id,   # per-file identifier for the push side-channel
    }), 200


@app.route('/interfaces', methods=['GET'])
def get_interfaces():
    """Return usable network interfaces (excluding loopback lo)."""
    try:
        result = subprocess.run(
            ['ip', '-o', 'link', 'show'],
            capture_output=True, text=True, timeout=5
        )
        env      = load_env_vars()
        current  = env.get('interface', '')
        ifaces   = []
        for line in result.stdout.split('\n'):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            iface = parts[1].rstrip(':')
            if iface == 'lo':
                continue
            ifaces.append({'name': iface, 'active': iface == current})
        return jsonify({'interfaces': ifaces, 'current': current}), 200
    except Exception as e:
        return jsonify({'interfaces': [], 'error': str(e)}), 200


@app.route('/set_interface', methods=['POST'])
def set_interface():
    """Switch active network interface (writes INTERFACE to .env)."""
    try:
        data      = request.get_json() or {}
        interface = data.get('interface', '').strip()
        if not interface:
            return jsonify({'success': False, 'error': 'interface is required'}), 400
        if interface == 'lo':
            return jsonify({'success': False, 'error': 'Cannot use loopback interface'}), 400

        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        lines, found = [], False
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    if line.startswith('INTERFACE='):
                        lines.append(f'INTERFACE={interface}\n')
                        found = True
                    else:
                        lines.append(line)
        if not found:
            lines.append(f'INTERFACE={interface}\n')
        with open(env_path, 'w') as f:
            f.writelines(lines)

        print(f'[set_interface] Switched to: {interface}')
        return jsonify({'success': True, 'interface': interface}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/set_dirs', methods=['POST'])
def set_dirs():
    """Update OUTDIR and/or SRCDIR in .env."""
    try:
        data     = request.get_json() or {}
        out_dir  = data.get('outdir', '').strip()
        src_dir  = data.get('srcdir', '').strip()

        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        lines = []
        found_out, found_src = False, False
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    if out_dir and line.startswith('OUTDIR='):
                        lines.append(f'OUTDIR={out_dir}\n')
                        found_out = True
                    elif src_dir and line.startswith('SRCDIR='):
                        lines.append(f'SRCDIR={src_dir}\n')
                        found_src = True
                    else:
                        lines.append(line)
        if out_dir and not found_out:
            lines.append(f'OUTDIR={out_dir}\n')
        if src_dir and not found_src:
            lines.append(f'SRCDIR={src_dir}\n')
        with open(env_path, 'w') as f:
            f.writelines(lines)

        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/update/check', methods=['GET'])
def update_check():
    """Compare local .version SHA with latest commit on GitHub."""
    import urllib.request as _ureq
    try:
        app_dir   = os.path.dirname(os.path.abspath(__file__))
        ver_file  = os.path.join(app_dir, '.version')
        local_sha = 'dev'
        if os.path.exists(ver_file):
            with open(ver_file) as f:
                local_sha = f.read().strip() or 'dev'

        owner, repo, branch = 'karthikvvk', 'LANFXplorer', 'main'
        env   = load_env_vars()
        token = env.get('github_token', '') or os.environ.get('GITHUB_TOKEN', '')

        hdrs = {'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'LANFXplorer-Updater'}
        if token:
            hdrs['Authorization'] = f'token {token}'

        api_url = f'https://api.github.com/repos/{owner}/{repo}/commits/{branch}'
        req = _ureq.Request(api_url, headers=hdrs)
        with _ureq.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        latest_sha  = data['sha']
        commit_msg  = data['commit']['message'].split('\n')[0]
        commit_date = data['commit']['committer']['date']

        return jsonify({
            'is_latest':      local_sha == latest_sha,
            'local_sha':      local_sha,
            'latest_sha':     latest_sha,
            'short_local':    local_sha[:8] if local_sha != 'dev' else 'dev',
            'short_latest':   latest_sha[:8],
            'commit_message': commit_msg,
            'commit_date':    commit_date,
        }), 200
    except Exception as e:
        print(f'[update/check] error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/update/apply', methods=['POST'])
def update_apply():
    """
    Smart update flow:
      1. Download tarball from GitHub
      2. Extract to update/
      3. Copy safe files to app root (skip .env, certs/, virtual/, update/, .version)
      4. pip install --upgrade -r requirements.txt inside virtual/
      5. Write new SHA to .version
      6. Cleanup (delete update/ and temp archive)
    """
    import urllib.request as _ureq
    import tarfile, shutil

    app_dir     = os.path.dirname(os.path.abspath(__file__))
    update_dir  = os.path.join(app_dir, 'update')
    archive_tmp = os.path.join(app_dir, '_update_dl.tar.gz')

    owner, repo, branch = 'karthikvvk', 'LANFXplorer', 'main'
    env   = load_env_vars()
    token = env.get('github_token', '') or os.environ.get('GITHUB_TOKEN', '')

    hdrs = {'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'LANFXplorer-Updater'}
    if token:
        hdrs['Authorization'] = f'token {token}'

    # Files/dirs that must never be overwritten during an update
    SKIP = {'.env', 'certs', 'update', 'virtual', '__pycache__',
            '.version', 'peer_store.json', 'logs'}

    try:
        # ── Step 1: Download tarball ──────────────────────────────────────
        tarball_url = f'https://api.github.com/repos/{owner}/{repo}/tarball/{branch}'
        print(f'[update] Downloading {tarball_url}')
        req = _ureq.Request(tarball_url, headers=hdrs)
        with _ureq.urlopen(req, timeout=120) as resp:
            with open(archive_tmp, 'wb') as fh:
                fh.write(resp.read())
        print(f'[update] Download complete → {archive_tmp}')

        # ── Step 2: Extract to update/ ────────────────────────────────────
        if os.path.exists(update_dir):
            shutil.rmtree(update_dir)
        os.makedirs(update_dir)
        with tarfile.open(archive_tmp, 'r:gz') as tar:
            tar.extractall(update_dir)

        # GitHub extracts into owner-repo-<sha>/ subdir
        subdirs = [d for d in os.listdir(update_dir)
                   if os.path.isdir(os.path.join(update_dir, d))]
        if not subdirs:
            raise RuntimeError('Archive contained no top-level directory')
        extracted_root = os.path.join(update_dir, subdirs[0])
        print(f'[update] Extracted root: {extracted_root}')

        # ── Step 3: Copy safe files to app_dir ───────────────────────────
        for item in os.listdir(extracted_root):
            if item in SKIP:
                continue
            src = os.path.join(extracted_root, item)
            dst = os.path.join(app_dir, item)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        print('[update] Files copied to app directory')

        # ── Step 4: pip upgrade ───────────────────────────────────────────
        venv_pip     = os.path.join(app_dir, 'virtual', 'bin', 'pip')
        requirements = os.path.join(app_dir, 'requirements.txt')
        if os.path.isfile(venv_pip) and os.path.isfile(requirements):
            print('[update] Upgrading pip packages…')
            subprocess.run(
                [venv_pip, 'install', '--upgrade', '-r', requirements],
                capture_output=True, timeout=180,
            )
        else:
            print('[update] Skipping pip upgrade (pip or requirements.txt not found)')

        # ── Step 5: Fetch latest SHA and write .version ──────────────────
        api_url = f'https://api.github.com/repos/{owner}/{repo}/commits/{branch}'
        req2    = _ureq.Request(api_url, headers=hdrs)
        with _ureq.urlopen(req2, timeout=10) as resp2:
            sha_data   = json.loads(resp2.read().decode())
        new_sha = sha_data['sha']
        with open(os.path.join(app_dir, '.version'), 'w') as vf:
            vf.write(new_sha)
        print(f'[update] Version written: {new_sha[:8]}')

        return jsonify({'success': True, 'sha': new_sha,
                        'short': new_sha[:8]}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

    finally:
        # ── Step 6: Cleanup ──────────────────────────────────────────────
        if os.path.exists(archive_tmp):
            os.remove(archive_tmp)
        if os.path.exists(update_dir):
            shutil.rmtree(update_dir)
        print('[update] Cleanup done')


if __name__ == "__main__":


    # start_peer_discovery()
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False
    )
