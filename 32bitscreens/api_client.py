"""
LANFXplorer – Python API Client
Mirrors the Flutter ApiService, talking to the Flask backend on localhost:5000.
All methods are synchronous (using requests) – call from background threads
when needed to avoid blocking the tkinter main loop.
"""

import requests
import os

BASE_URL = "http://127.0.0.1:5000"
_TIMEOUT = 10          # seconds for standard calls
_SCAN_TIMEOUT = 120    # network scan can be slow
_TRANSFER_TIMEOUT = 60


class ApiClient:
    """Stateless HTTP client for the Flask backend."""

    # ── credentials ─────────────────────────────────────────────────────────
    def check_password(self) -> bool:
        """Return True if a password is stored in the OS keyring."""
        try:
            r = requests.get(f"{BASE_URL}/check_password", timeout=_TIMEOUT)
            if r.status_code == 200:
                return r.json().get("has_password", False)
        except Exception:
            pass
        return False

    def set_password(self, password: str) -> bool:
        """Store *password* in the OS keyring."""
        try:
            r = requests.post(f"{BASE_URL}/set_password",
                              json={"password": password},
                              timeout=_TIMEOUT)
            if r.status_code == 200:
                return r.json().get("success", False)
        except Exception:
            pass
        return False

    # ── network ─────────────────────────────────────────────────────────────
    def scan_network(self) -> list:
        """GET /listhost – returns list of dicts with username/ip/os/status."""
        try:
            r = requests.get(f"{BASE_URL}/listhost", timeout=_SCAN_TIMEOUT,
                             headers={"Accept": "application/json"})
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return []

    def health(self) -> bool:
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def os_info(self, remote_host: str | None = None) -> dict | None:
        """POST /osinfo – returns OS/user info for a peer."""
        try:
            body = {}
            if remote_host:
                body["remote_host"] = remote_host
            r = requests.post(f"{BASE_URL}/osinfo", json=body,
                              timeout=_TIMEOUT)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    # ── file system ─────────────────────────────────────────────────────────
    def get_default_path(self, remote_host: str | None = None) -> str | None:
        """POST /default_path – returns the Lanfxplorer root on a peer."""
        try:
            body = {}
            if remote_host:
                body["remote_host"] = remote_host
            r = requests.post(f"{BASE_URL}/default_path", json=body,
                              timeout=_TIMEOUT)
            if r.status_code == 200:
                return r.json().get("default_path")
        except Exception:
            pass
        return None

    def list_directory(self, path: str,
                       remote_host: str | None = None) -> list | None:
        """POST /listdir – returns list of file dicts or None on error.
        Each dict: name, path, is_directory, size, mtime."""
        try:
            body = {"path": path}
            if remote_host:
                body["remote_host"] = remote_host
            r = requests.post(f"{BASE_URL}/listdir", json=body,
                              timeout=_TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                if data.get("type") == "directory":
                    return data.get("files", [])
        except Exception:
            pass
        return None

    # ── transfers ───────────────────────────────────────────────────────────
    def send_files(self, remote_host: str, files: list,
                   dest_dir: str | None = None) -> dict | None:
        """POST /send_files → returns {task_id, status, files} or None."""
        try:
            body = {"remote_host": remote_host, "files": files}
            if dest_dir:
                body["dest_dir"] = dest_dir
            r = requests.post(f"{BASE_URL}/send_files", json=body,
                              timeout=_TRANSFER_TIMEOUT)
            if r.status_code in (200, 202):
                return r.json()
        except Exception:
            pass
        return None

    def fetch_files(self, remote_host: str, files: list,
                    dest_dir: str | None = None) -> dict | None:
        """POST /receive_files → returns {status, remote_response} or None."""
        try:
            body = {"remote_host": remote_host, "files": files}
            if dest_dir:
                body["dest_dir"] = dest_dir
            r = requests.post(f"{BASE_URL}/receive_files", json=body,
                              timeout=_TRANSFER_TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                return data.get("remote_response", data)
        except Exception:
            pass
        return None

    def get_transfer_status(self, task_id: str) -> dict | None:
        """GET /transfer_status/<id> → {status, progress, …}."""
        try:
            r = requests.get(f"{BASE_URL}/transfer_status/{task_id}",
                             timeout=_TIMEOUT)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    # ── handshake ───────────────────────────────────────────────────────────
    def handshake(self, dest_host: str, password: str) -> dict:
        """POST /handshake → {success: bool, error?: str}."""
        try:
            r = requests.post(f"{BASE_URL}/handshake",
                              json={"dest_host": dest_host,
                                    "password": password},
                              timeout=100)
            if r.status_code in (200, 401):
                return r.json()
            return {"success": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── environment ─────────────────────────────────────────────────────────
    def reset_environment(self) -> bool:
        """POST /reset_environment."""
        try:
            r = requests.post(f"{BASE_URL}/reset_environment",
                              timeout=_TIMEOUT)
            return r.status_code == 200
        except Exception:
            return False

    # ── file operations ─────────────────────────────────────────────────────
    def create_file(self, path: str,
                    remote_host: str | None = None) -> bool:
        body = {"path": path}
        if remote_host:
            body["remote_host"] = remote_host
        try:
            r = requests.post(f"{BASE_URL}/create_file", json=body,
                              timeout=_TIMEOUT)
            return r.status_code == 200
        except Exception:
            return False

    def create_folder(self, path: str,
                      remote_host: str | None = None) -> bool:
        body = {"path": path}
        if remote_host:
            body["remote_host"] = remote_host
        try:
            r = requests.post(f"{BASE_URL}/create_folder", json=body,
                              timeout=_TIMEOUT)
            return r.status_code == 200
        except Exception:
            return False

    def delete_item(self, path: str,
                    remote_host: str | None = None) -> bool:
        body = {"path": path}
        if remote_host:
            body["remote_host"] = remote_host
        try:
            r = requests.post(f"{BASE_URL}/delete_item", json=body,
                              timeout=_TIMEOUT)
            return r.status_code == 200
        except Exception:
            return False
