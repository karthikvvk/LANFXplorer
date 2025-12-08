import streamlit as st
import os
from pathlib import Path
import requests
import json

st.set_page_config(page_title="P2P File Browser", page_icon="📁", layout="wide")

API_BRIDGE_BASE = "http://localhost:5000"  # assumes api_bridge runs locally

st.markdown("""
<style>
    .stButton button { width: 100%; }
</style>
""", unsafe_allow_html=True)


# ---------- Helpers ----------

def fetch_peers():
    """Call local api_bridge /listhost to get list of peers."""
    try:
        resp = requests.get(f"{API_BRIDGE_BASE}/listhost", timeout=3)
        if resp.status_code == 200:
            return resp.json()
        else:
            return []
    except Exception:
        return []


def remote_listdir(remote_host: str, path: str):
    """Call /listdir on a remote host."""
    try:
        resp = requests.post(
            f"http://{remote_host}:5000/listdir",
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
    """Call local /send_files to trigger QUIC sender."""
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
            # Default remote path: for simplicity, start at '/'
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
            # we don't know type without another call; simple heuristic:
            # try to descend by clicking -> call listdir again
            btn_key = f"{key_prefix}_entry_{full_path}"
            if st.button(item, key=btn_key, use_container_width=True):
                # naive approach: assume it's a dir and try to ls; if error, will show
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

if "selected_remote_host" not in st.session_state:
    st.session_state.selected_remote_host = None


# ---------- UI ----------
st.title("🔄 P2P File Browser (QUIC)")

# Sidebar: peer selection
with st.sidebar:
    st.subheader("🧑‍💻 Peers")
    peers = fetch_peers()
    if not peers:
        st.warning("No peers found via /listhost")
        st.write("Make sure api_bridge is running and subnet scanning works.")
    else:
        options = [f"{p['host']} ({p.get('user') or 'unknown'} / {p.get('os')})" for p in peers]
        host_map = {opt: p["host"] for opt, p in zip(options, peers)}

        default_opt = options[0]
        selected_opt = st.selectbox("Select remote host", options, index=0)
        st.session_state.selected_remote_host = host_map[selected_opt]

        st.caption(f"Selected remote: {st.session_state.selected_remote_host}")

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

    if st.session_state.selected_remote_host and st.session_state.selected_local_files:
        if st.button("📤 Send selected to remote", use_container_width=True):
            with st.spinner("Sending files via QUIC..."):
                resp = send_files_to_remote(
                    st.session_state.selected_remote_host,
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
    if not st.session_state.selected_remote_host:
        st.info("Select a remote host in the sidebar.")
    else:
        render_remote_tree(
            st.session_state.selected_remote_host,
            "remote_path",
            "remote"
        )
