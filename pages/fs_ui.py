# pages/2_File_Manager.py
import streamlit as st
import requests
import os
from pathlib import Path
from startsetup import load_env_vars
from dotenv import load_dotenv

st.set_page_config(page_title="QUIC File Transfer", page_icon="📁", layout="wide")
load_dotenv()

st.markdown("""
<style>
    .stButton button { width: 100%; }
</style>
""", unsafe_allow_html=True)


def load_config():
    """Load environment/config via startsetup.load_env_vars()"""
    try:
        env = load_env_vars()
        if not isinstance(env, dict):
            return {}
        return env
    except Exception:
        return {}


def call_api(endpoint, data, base_url):
    """Make API call to peer"""
    if not base_url:
        return None, f"Base URL not configured for endpoint {endpoint}"
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    try:
        resp = requests.post(url, json=data)
        resp.raise_for_status()
        try:
            return resp.json(), None
        except ValueError:
            return None, f"Invalid JSON response from {url}"
    except requests.exceptions.RequestException as e:
        return None, str(e)

def render_tree(base_url, path_state_key, key_prefix, selected_key):
    """Render file tree for a peer"""
    try:
        current_path = st.session_state.get(path_state_key, "/")
        if not current_path:
            current_path = "/" if os.name != 'nt' else str(Path.home())
            st.session_state[path_state_key] = current_path

        # Parent navigation
        parent = os.path.dirname(current_path.rstrip("/\\"))
        cols = st.columns([1, 9])
        with cols[0]:
            # Don't show up button at root
            can_go_up = parent and parent != current_path
            if can_go_up and st.button("⬆️", key=f"{key_prefix}_up_{current_path}", help="Go up"):
                st.session_state[path_state_key] = parent or ("/" if os.name != 'nt' else "C:\\")
                st.rerun()
        with cols[1]:
            st.markdown(f"**`{current_path}`**")

        if not base_url:
            st.warning("API endpoint not configured")
            return

        # List directory
        resp, err = call_api("listdir", {"path": current_path}, base_url)
        if err:
            st.error(f"Failed to list directory: {err}")
            return
        
        if not isinstance(resp, dict):
            st.error(f"Invalid response format: {resp}")
            return
            
        # Handle if current path is actually a file
        if resp.get("type") == "file":
            st.info("📄 This is a file, not a directory")
            return
        
        items = resp.get("files", [])
        if not items:
            st.info("📂 Empty directory")
            return

        if selected_key not in st.session_state:
            st.session_state[selected_key] = []

        # Render items
        for item in items:
            # Build full path properly for both Windows and Linux
            if current_path.endswith(os.sep):
                full_path = current_path + item
            else:
                full_path = os.path.join(current_path, item)
            
            # Probe to check if it's a directory
            probe, probe_err = call_api("listdir", {"path": full_path}, base_url)
            
            # Determine if it's a directory based on response
            is_directory = False
            if not probe_err and isinstance(probe, dict):
                is_directory = (probe.get("type") == "directory")

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
        st.error(f"Error rendering tree: {e}")
        import traceback
        st.code(traceback.format_exc())  # Show full traceback for debugging

# ---------- Session State Init ----------
if "local_path" not in st.session_state:
    st.session_state.local_path = str(Path.home())

if "remote_path" not in st.session_state:
    st.session_state.remote_path = "/"

if "selected_local_files" not in st.session_state:
    st.session_state.selected_local_files = []

if "selected_remote_files" not in st.session_state:
    st.session_state.selected_remote_files = []

if "_config" not in st.session_state:
    st.session_state._config = load_config()

# Handle navigation from host selector
if st.session_state.get("goto_page") == "file_manager":
    remote = st.session_state.get("REMOTE_HOST") or os.environ.get("DEST_HOST")
    if remote:
        st.session_state["remote_override_api"] = f"http://{remote}:5000"
    st.session_state.pop("goto_page", None)

# ---------- Load Config ----------
config = st.session_state._config or {}
host_ip = config.get("host") or config.get("host_ip") or ""
dest_host = (config.get("dest_host") or config.get("dest") or 
             os.environ.get("DEST_HOST") or "")

# API endpoints
LOCAL_API = (st.session_state.get("local_override_api") or 
             (f"http://{host_ip}:5000" if host_ip else ""))
REMOTE_API = (st.session_state.get("remote_override_api") or 
              (f"http://{dest_host}:5000" if dest_host else ""))

# ---------- UI ----------
st.title("📁 QUIC File Transfer")

# Navigation bar
nav_col1, nav_col2 = st.columns([1, 9])
with nav_col1:
    if st.button("⬅️ Change Host"):
        for k in ("REMOTE_HOST", "REMOTE_USER", "REMOTE_PASS", "remote_override_api"):
            st.session_state.pop(k, None)
        try:
            st.switch_page("1_Select_Host")
        except Exception:
            st.session_state["goto_page"] = "host_selector"
            st.rerun()
with nav_col2:
    st.markdown(f"**Local:** `{host_ip or 'localhost'}` ⟷ **Remote:** `{dest_host or 'Not set'}`")

# Debug info
with st.expander("🔧 Debug Info"):
    st.json({
        "local_api": LOCAL_API,
        "remote_api": REMOTE_API,
        "local_path": st.session_state.get("local_path"),
        "remote_path": st.session_state.get("remote_path"),
        "selected_local": len(st.session_state.get("selected_local_files", [])),
        "selected_remote": len(st.session_state.get("selected_remote_files", []))
    })

# Main layout
col_local, col_actions, col_remote = st.columns([5, 2, 5])

with col_local:
    st.subheader("💻 Local Files")
    st.caption(f"API: {LOCAL_API or 'Not configured'}")
    render_tree(LOCAL_API, "local_path", "local", "selected_local_files")
    
    if st.session_state.selected_local_files:
        st.info(f"✅ {len(st.session_state.selected_local_files)} file(s) selected")

with col_actions:
    st.subheader("⚡ Actions")
    
    # Transfer Local → Remote
    st.markdown("**Transfer TO Remote:**")
    st.code(st.session_state.get("remote_path", "/"), language=None)
    
    if st.button("➡️ Transfer →", use_container_width=True, key="transfer_to_remote"):
        remote_dir = st.session_state.get("remote_path", "/")
        if not remote_dir:
            st.error("Remote path not set")
        elif not st.session_state.selected_local_files:
            st.warning("No local files selected")
        else:
            for src_path in list(st.session_state.selected_local_files):
                # Construct destination path: remote_dir + filename
                filename = os.path.basename(src_path)
                dest_path = os.path.join(remote_dir, filename)
                
                data = {"src": src_path, "dest": dest_path}
                result, error = call_api("transfer", data, LOCAL_API)
                if error:
                    st.error(f"❌ {filename}: {error}")
                else:
                    st.success(f"✅ Transferred {filename}")
            st.session_state.selected_local_files = []
            st.rerun()
    st.divider()

    # Transfer Remote → Local (using transferremote)
    st.markdown("**Transfer FROM Remote:**")
    st.code(st.session_state.get("local_path", str(Path.home())), language=None)
    
    if st.button("⬅️ ← Transfer", use_container_width=True, key="transfer"):
        local_dir = st.session_state.get("local_path", str(Path.home()))
        if not local_dir:
            st.error("Local path not set")
        elif not dest_host:
            st.error("Remote host not configured")
        elif not host_ip:
            st.error("Local host IP not configured")
        elif not st.session_state.selected_remote_files:
            st.warning("No remote files selected")
        else:
            for src_path in list(st.session_state.selected_remote_files):
                # Construct destination path: local_dir + filename
                filename = os.path.basename(src_path)
                dest_path = os.path.join(local_dir, filename)
                
                data = {
                    "src": src_path,              # File path on remote host
                    "dest": dest_path,            # File path on local (Docker)
                    "source_host": dest_host,     # Remote host IP (has the file)
                    "dest_host": host_ip,         # Local Docker IP (destination)
                    "port": 4433                  # QUIC port
                }
                
                st.write(f"Debug: Calling transferremote with data: {data}")  # DEBUG
                
                # Call transferremote on LOCAL API (Docker)
                result, error = call_api("transferremote", data, LOCAL_API)

                if error:
                    st.error(f"❌ {filename}: {error}")
                    st.write(f"Error details: {error}")  # DEBUG
                else:
                    st.success(f"✅ Downloaded {filename}")
                    st.write(f"Result: {result}")  # DEBUG
            st.session_state.selected_remote_files = []
            st.rerun()

with col_remote:
    st.subheader("☁️ Remote Files")
    st.caption(f"API: {REMOTE_API or 'Not configured'}")
    render_tree(REMOTE_API, "remote_path", "remote", "selected_remote_files")
    
    if st.session_state.selected_remote_files:
        st.info(f"✅ {len(st.session_state.selected_remote_files)} file(s) selected")