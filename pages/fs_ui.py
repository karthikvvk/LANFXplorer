# pages/fs_ui.py
import streamlit as st
import os
from pathlib import Path

st.set_page_config(page_title="File Browser", page_icon="📁", layout="wide")

st.markdown("""
<style>
    .stButton button { width: 100%; }
</style>
""", unsafe_allow_html=True)

def render_tree(path_state_key, key_prefix, selected_key):
    """Render local file tree browser"""
    try:
        current_path = st.session_state.get(path_state_key, str(Path.home()))
        if not current_path:
            current_path = str(Path.home())
            st.session_state[path_state_key] = current_path

        # Parent navigation
        parent = os.path.dirname(current_path.rstrip("/\\"))
        cols = st.columns([1, 9])
        with cols[0]:
            # Don't show up button at root
            can_go_up = parent and parent != current_path
            if can_go_up and st.button("⬆️", key=f"{key_prefix}_up_{current_path}", help="Go up"):
                st.session_state[path_state_key] = parent
                st.rerun()
        with cols[1]:
            st.markdown(f"**`{current_path}`**")

        # Check if path exists
        if not os.path.exists(current_path):
            st.error(f"Path does not exist: {current_path}")
            return

        # Check if it's a directory
        if not os.path.isdir(current_path):
            st.info("📄 This is a file, not a directory")
            return
        
        # List directory
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

        # Render items
        for item in items:
            # Build full path
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
        st.error(f"Error rendering tree: {e}")
        import traceback
        st.code(traceback.format_exc())

# ---------- Session State Init ----------
if "local_path" not in st.session_state:
    st.session_state.local_path = str(Path.home())

if "selected_local_files" not in st.session_state:
    st.session_state.selected_local_files = []

if "selected_remote_files" not in st.session_state:
    st.session_state.selected_remote_files = []

# ---------- UI ----------
st.title("📁 File Browser")

# Debug info
with st.expander("🔧 Session State"):
    st.json({
        "local_path": st.session_state.get("local_path"),
        "selected_local": len(st.session_state.get("selected_local_files", [])),
        "selected_remote": len(st.session_state.get("selected_remote_files", []))
    })

# Main layout
col_local, col_info = st.columns([3, 2])

with col_local:
    st.subheader("💻 Local Files")
    render_tree("local_path", "local", "selected_local_files")
    
    if st.session_state.selected_local_files:
        st.info(f"✅ {len(st.session_state.selected_local_files)} file(s) selected")
        st.write("**Selected Files:**")
        for f in st.session_state.selected_local_files:
            st.code(f, language=None)
        
        if st.button("🗑️ Clear Selection", use_container_width=True):
            st.session_state.selected_local_files = []
            st.rerun()

with col_info:
    st.subheader("📊 Info")
    st.write("**Selected Files:**")
    st.info(f"{len(st.session_state.selected_local_files)} file(s)")
    
    if st.session_state.selected_local_files:
        st.divider()
        st.write("**File Details:**")
        for filepath in st.session_state.selected_local_files:
            if os.path.exists(filepath):
                size = os.path.getsize(filepath)
                st.caption(f"📄 {os.path.basename(filepath)} ({size:,} bytes)")