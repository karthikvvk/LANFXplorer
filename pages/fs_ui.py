# pages/fs_ui.py
import streamlit as st
import os
from pathlib import Path
import requests
import json
import ntpath
import posixpath
from typing import Iterable, Union
from startsetup import load_env_vars

st.set_page_config(page_title="P2P File Browser", page_icon="📁", layout="wide")

# ------------------------------------------
# Path Resolver (Remote OS Aware)
# ------------------------------------------

PathLike = Union[str, Iterable[str]]

def pathresolver(path: PathLike,
                 *,
                 remote_os: str | None = None,
                 base: str | None = None) -> str:
    if remote_os is None:
        remote_os = (st.session_state.get("REMOTE_OS") or "linux").lower()
    else:
        remote_os = remote_os.lower()

    pmod = ntpath if remote_os.startswith("win") else posixpath

    if isinstance(path, str):
        target = path
    else:
        segments = list(path)
        target = segments[0] if segments else ""
        for seg in segments[1:]:
            target = pmod.join(target, seg)

    if base:
        if remote_os.startswith("win"):
            is_abs = pmod.isabs(target) or (len(target) >= 2 and target[1] == ":")
        else:
            is_abs = pmod.isabs(target)

        if not is_abs:
            target = pmod.join(base, target)

    return pmod.normpath(target)


# ------------------------------------------
# Env, API Binding
# ------------------------------------------

env = load_env_vars()

local_host = env.get("host") or "127.0.0.1"
API_BRIDGE_BASE = f"http://{local_host}:5000"

remote_host = st.session_state.get("REMOTE_HOST") or env.get("dest_host")
remote_os = st.session_state.get("REMOTE_OS", "linux")

remote_override_api = st.session_state.get("remote_override_api")

st.markdown("""
<style>
    .stButton button { width: 100%; }
</style>
""", unsafe_allow_html=True)


# ------------------------------------------
# Remote API Helpers
# ------------------------------------------

def remote_listdir(remote_host: str, path: str):
    try:
        api_base = (remote_override_api or f"http://{remote_host}:5000").rstrip("/")
        resp = requests.post(f"{api_base}/listdir", json={"path": path}, timeout=5)
        return resp.json() if resp.status_code == 200 else {"status": "error", "message": resp.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def send_files_to_remote(remote_host: str, files: list[str]):
    try:
        resp = requests.post(
            f"{API_BRIDGE_BASE}/send_files",
            json={"remote_host": remote_host, "files": files},
            timeout=60,
        )
        return resp
    except Exception as e:
        return e


# ------------------------------------------
# Local Tree Renderer
# ------------------------------------------

def render_local_tree(path_state_key, key_prefix, selected_key):
    current_path = st.session_state.get(path_state_key, str(Path.home()))
    st.session_state[path_state_key] = current_path

    parent = os.path.dirname(current_path.rstrip("/\\"))
    cols = st.columns([1, 9])
    with cols[0]:
        if parent != current_path and st.button("⬆️", key=f"{key_prefix}_up", help="Up"):
            st.session_state[path_state_key] = parent
            st.rerun()
    with cols[1]:
        st.markdown(f"**`{current_path}`**")

    if not os.path.exists(current_path):
        st.error(f"Path not exists: {current_path}")
        return

    try:
        items = sorted(os.listdir(current_path))
    except Exception as e:
        st.error(str(e))
        return

    st.session_state.setdefault(selected_key, [])

    for item in items:
        full_path = os.path.join(current_path, item)
        if os.path.isdir(full_path):
            if st.button(f"📁 {item}", key=f"{key_prefix}_folder_{full_path}"):
                st.session_state[path_state_key] = full_path
                st.rerun()
        else:
            checked = st.checkbox(f"📄 {item}", key=f"{key_prefix}_file_{full_path}",
                                 value=(full_path in st.session_state[selected_key]))
            if checked:
                if full_path not in st.session_state[selected_key]:
                    st.session_state[selected_key].append(full_path)
            else:
                if full_path in st.session_state[selected_key]:
                    st.session_state[selected_key].remove(full_path)


# ------------------------------------------
# Remote Tree Renderer
# ------------------------------------------

def render_remote_tree(remote_host: str, path_state_key: str, key_prefix: str):
    current_path = pathresolver(st.session_state.get(path_state_key, "/"), remote_os=remote_os)
    st.session_state[path_state_key] = current_path

    parent = pathresolver(posixpath.dirname(current_path), remote_os=remote_os)

    cols = st.columns([1, 9])
    with cols[0]:
        if parent != current_path and st.button("⬆️", key=f"{key_prefix}_up", help="Up"):
            st.session_state[path_state_key] = parent
            st.rerun()
    with cols[1]:
        st.markdown(f"**`{remote_host}:{current_path}`**")

    result = remote_listdir(remote_host, current_path)
    if result.get("status") != "success":
        st.error(result.get("message"))
        return

    if result.get("type") == "file":
        info = result.get("info", {})
        st.info(f"📄 {info.get('path')} ({info.get('size', 0)} bytes)")
        return

    files = result.get("files", [])
    for item in files:
        full_path = pathresolver([current_path, item], remote_os=remote_os)
        if st.button(f"{item}", key=f"{key_prefix}_{full_path}", use_container_width=True):
            st.session_state[path_state_key] = full_path
            st.rerun()


# ------------------------------------------
# Initial Session State
# ------------------------------------------

st.session_state.setdefault("local_path", str(Path.home()))
st.session_state.setdefault("selected_local_files", [])
st.session_state.setdefault("remote_path", "/")

if "REMOTE_HOST" not in st.session_state and remote_host:
    st.session_state["REMOTE_HOST"] = remote_host


# ------------------------------------------
# UI Layout
# ------------------------------------------

st.title("🔄 P2P File Browser (QUIC)")

with st.sidebar:
    st.subheader("🔧 Status")
    st.write("Local API Bridge:")
    st.code(API_BRIDGE_BASE)

    if remote_host:
        st.success(f"Remote: {remote_host} ({remote_os})")
    else:
        st.error("Select host in 'Select Host' page")
        st.stop()


col_local, col_remote = st.columns([3, 3])

with col_local:
    st.subheader("💻 Local Files")
    render_local_tree("local_path", "local", "selected_local_files")
    st.divider()
    if st.session_state.selected_local_files:
        if st.button("📤 Send to Remote", use_container_width=True):
            resp = send_files_to_remote(
                st.session_state["REMOTE_HOST"],
                st.session_state["selected_local_files"]
            )
            try:
                data = resp.json()
                if data.get("status") == "success":
                    st.success("Transfer complete!")
                else:
                    st.error(str(data))
            except:
                st.error("Invalid server response!")

with col_remote:
    st.subheader("📡 Remote Files")
    render_remote_tree(
        st.session_state["REMOTE_HOST"],
        "remote_path",
        "remote"
    )
