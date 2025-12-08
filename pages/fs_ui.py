# pages/fs_ui.py
import streamlit as st
import os
from pathlib import Path
import requests
import json
from startsetup import load_env_vars
import ntpath
import posixpath
from typing import Iterable, Union


st.set_page_config(page_title="P2P File Browser", page_icon="📁", layout="wide")

# ---------- Env + Session Integration ----------




PathLike = Union[str, Iterable[str]]

def pathresolver(path: PathLike,
                 *,
                 remote_os: str | None = None,
                 base: str | None = None) -> str:
    """
    Resolve a path for the *remote* host, using its OS type.

    - `path` can be:
        - a string: "Downloads/file.txt"
        - a list/tuple: ["Downloads", "file.txt"]
    - `remote_os`:
        - "windows", "win32", etc. => use ntpath
        - anything else => use posixpath
        - if None => use st.session_state["REMOTE_OS"] or default "linux"
    - `base`:
        - optional remote base directory
        - if given and `path` is relative, we join base + path
    """

    # 1) Determine OS type
    if remote_os is None:
        remote_os = (st.session_state.get("REMOTE_OS") or "linux").lower()
    else:
        remote_os = remote_os.lower()

    if remote_os.startswith("win"):
        pmod = ntpath
    else:
        pmod = posixpath

    # 2) Normalize `path` to a string or join segments
    if isinstance(path, str):
        target = path
    else:
        # assume iterable of segments
        segments = list(path)
        if not segments:
            target = ""
        else:
            target = segments[0]
            for seg in segments[1:]:
                target = pmod.join(target, seg)

    # 3) If base is provided and target is relative, join base + target
    if base:
        # For Windows, treat drive letter or leading slash as absolute
        if remote_os.startswith("win"):
            is_abs = pmod.isabs(target) or (len(target) >= 2 and target[1] == ":")
        else:
            is_abs = pmod.isabs(target)

        if not is_abs:
            target = pmod.join(base, target)

    # 4) Normalize slashes etc.
    target = pmod.normpath(target)

    return target




env = load_env_vars()

# Local machine where api_bridge.py is running
local_host = env.get("host") or "127.0.0.1"
local_port = env.get("port") or 5000  # api_bridge is 5000, QUIC is 4433
API_BRIDGE_BASE = f"http://{local_host}:5000"

# Remote peer (receiver side) selected via host_selectorui.py
remote_host = st.session_state.get("REMOTE_HOST") or env.get("dest_host")

# Remote override API base if set (from host_selectorui)
remote_override_api = st.session_state.get("remote_override_api")
# If override exists, use it for /listdir; otherwise, we’ll use http://<remote_host>:5000

st.markdown("""
<style>
    .stButton button { width: 100%; }
</style>
""", unsafe_allow_html=True)


# ---------- Helpers ----------

def remote_listdir(remote_host: str, path: str):
    """Call /listdir on a remote host."""
    try:
        if remote_override_api:
            base = remote_override_api.rstrip("/")
        else:
            base = f"http://{remote_host}:5000"

        resp = requests.post(
            f"{base}/listdir",
            json={"path": path},
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            return {"status": "error", "message": resp.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def send_files_to_remote(remote_host: str, files: list[str]):
    """
    Call local /send_files on our api_bridge to trigger QUIC sender.
    remote_host is still passed in JSON so /send_files can override DEST_HOST.
    """
    try:
        resp = requests.post(
            f"{API_BRIDGE_BASE}/send_files",
            json={"remote_host": remote_host, "files": files},
            timeout=60,
        )
        return resp
    except Exception as e:
        return e


# ---------- UI Components ----------

def render_local_tree(path_state_key, key_prefix, selected_key):
    """Render local file tree browser (sender side)"""
    try:
        current_path = st.session_state.get(path_state_key, str(Path.home()))
        if not current_path:
            current_path = str(Path.home())
            st.session_state[path_state_key] = current_path

        parent = os.path.dirname(current_path.rstrip("/\\"))
        cols = st.columns([1, 9])
        with cols[0]:
            can_go_up = parent and parent != current_path
            if can_go_up and st.button("⬆️", key=f"{key_prefix}_up_{current_path}", help="Go up"):
                st.session_state[path_state_key] = parent
                st.rerun()
        with cols[1]:
            st.markdown(f"**`{current_path}`**")

        if not os.path.exists(current_path):
            st.error(f"Path does not exist: {current_path}")
            return

        if not os.path.isdir(current_path):
            st.info("📄 This is a file, not a directory")
            return
        
        try:
            items = sorted(os.listdir(current_path))
        except PermissionError:
            st.error(f"Permission denied: {current_path}")
            return
        
        if not items:
            st.info("📂 Empty directory")
            return

        if selected_key not in st.session_state:
            st.session_state[selected_key] = []

        for item in items:
            full_path = os.path.join(current_path, item)
            is_directory = os.path.isdir(full_path)

            if is_directory:
                btn_key = f"{key_prefix}_folder_{full_path}"
                if st.button(f"📁 {item}", key=btn_key, use_container_width=True):
                    st.session_state[path_state_key] = full_path
                    st.rerun()
            else:
                cb_key = f"{key_prefix}_file_{full_path}"
                checked = st.checkbox(
                    f"📄 {item}", 
                    key=cb_key,
                    value=(full_path in st.session_state[selected_key])
                )
                if checked and full_path not in st.session_state[selected_key]:
                    st.session_state[selected_key].append(full_path)
                if (not checked) and (full_path in st.session_state[selected_key]):
                    st.session_state[selected_key].remove(full_path)
                    
    except Exception as e:
        st.error(f"Error rendering local tree: {e}")
        import traceback
        st.code(traceback.format_exc())


def render_remote_tree(remote_host: str, path_state_key: str, key_prefix: str):
    """Render remote file tree browser (receiver side) using /listdir on remote peer."""
    try:
        current_path = st.session_state.get(path_state_key)
        if not current_path:
            # Default remote path: start at '/'
            current_path = "/"
            st.session_state[path_state_key] = current_path

        # Parent nav
        parent = os.path.dirname(current_path.rstrip("/\\"))
        cols = st.columns([1, 9])
        with cols[0]:
            can_go_up = parent and parent != current_path
            if can_go_up and st.button("⬆️", key=f"{key_prefix}_up_{current_path}", help="Go up"):
                st.session_state[path_state_key] = parent or "/"
                st.rerun()
        with cols[1]:
            st.markdown(f"**`{remote_host}:{current_path}`**")

        # Fetch directory listing from remote
        result = remote_listdir(remote_host, current_path)
        if result.get("status") != "success":
            st.error(f"Remote listdir error: {result.get('message')}")
            return

        if result.get("type") == "file":
            info = result.get("info", {})
            st.info(f"📄 File: {info.get('path')} ({info.get('size', 0)} bytes)")
            return

        items = result.get("files", [])
        if not items:
            st.info("📂 Empty directory")
            return

        for item in items:
            full_path = os.path.join(result.get("path", current_path), item)
            btn_key = f"{key_prefix}_entry_{full_path}"
            if st.button(item, key=btn_key, use_container_width=True):
                st.session_state[path_state_key] = full_path
                st.rerun()

    except Exception as e:
        st.error(f"Error rendering remote tree: {e}")
        import traceback
        st.code(traceback.format_exc())


# ---------- Session State Init ----------
if "local_path" not in st.session_state:
    st.session_state.local_path = str(Path.home())

if "selected_local_files" not in st.session_state:
    st.session_state.selected_local_files = []

if "remote_path" not in st.session_state:
    st.session_state.remote_path = "/"

# If host_selector set REMOTE_HOST, keep it; else write from env
if "REMOTE_HOST" not in st.session_state and remote_host:
    st.session_state["REMOTE_HOST"] = remote_host


# ---------- UI ----------
st.title("🔄 P2P File Browser (QUIC)")

with st.sidebar:
    st.subheader("🔧 Context")
    st.write("**Local api_bridge:**")
    st.code(API_BRIDGE_BASE, language=None)

    st.write("**Remote host (receiver):**")
    if st.session_state.get("REMOTE_HOST"):
        st.success(st.session_state["REMOTE_HOST"])
        if remote_override_api:
            st.caption(f"Remote API override: {remote_override_api}")
        st.caption("Set by Select Host page or DEST_HOST in .env")
    else:
        st.error("No REMOTE_HOST set. Go to 'Select Host' page first.")
        st.stop()  # stop rendering rest of page


# Main layout: left = local (sender), right = remote (receiver)
col_local, col_remote = st.columns([3, 3])

with col_local:
    st.subheader("💻 Local (Sender)")
    render_local_tree("local_path", "local", "selected_local_files")
    
    if st.session_state.selected_local_files:
        st.info(f"✅ {len(st.session_state.selected_local_files)} file(s) selected")
        st.write("**Selected Files:**")
        for f in st.session_state.selected_local_files:
            st.code(f, language=None)
        
        if st.button("🗑️ Clear Selection", use_container_width=True):
            st.session_state.selected_local_files = []
            st.rerun()

    st.divider()

    remote_host_effective = st.session_state.get("REMOTE_HOST")
    if remote_host_effective and st.session_state.selected_local_files:
        if st.button("📤 Send selected to remote", use_container_width=True):
            with st.spinner("Sending files via QUIC..."):
                resp = send_files_to_remote(
                    remote_host_effective,
                    st.session_state.selected_local_files,
                )
                if isinstance(resp, Exception):
                    st.error(f"Send error: {resp}")
                else:
                    try:
                        data = resp.json()
                        if resp.status_code == 200 and data.get("status") == "success":
                            st.success(f"Sent {len(data.get('sent', []))} file(s) to {data.get('remote_host')}")
                            if data.get("missing"):
                                st.warning(f"Missing files: {data['missing']}")
                        else:
                            st.error(f"Send failed: {data}")
                    except Exception as e:
                        st.error(f"Invalid response from bridge: {e}")

with col_remote:
    st.subheader("📡 Remote (Receiver)")
    remote_host_effective = st.session_state.get("REMOTE_HOST")
    if not remote_host_effective:
        st.info("No remote host. Select one in the 'Select Host' page.")
    else:
        render_remote_tree(
            remote_host_effective,
            "remote_path",
            "remote"
        )
