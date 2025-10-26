import streamlit as st
import paramiko
import requests

# ---------- Remote connection details ----------
REMOTE_HOST = "192.168.0.104"
FLASK_BACKEND = "http://192.168.0.101:5000"

# ---------- Initialize Session State ----------
if "remote_user" not in st.session_state:
    val = requests.get(f"{FLASK_BACKEND}/connect")
    os_type, username = val.json().get("os"), val.json().get("user")

    st.session_state.remote_user = username
    st.session_state.os_type = os_type
    st.session_state.remote_pass = "1970"

    # Manual OS-based path setup
    if os_type == "windows":
        st.session_state.pwd = f"C:\\Users\\{username}\\"
        st.session_state.path_sep = "\\"
    else:
        st.session_state.pwd = f"/home/{username}/"
        st.session_state.path_sep = "/"

# ---------- Ensure path_sep exists ----------
if "path_sep" not in st.session_state:
    if "os_type" in st.session_state:
        st.session_state.path_sep = "\\" if st.session_state.os_type == "windows" else "/"
    else:
        st.session_state.path_sep = "/"

if "selected_item" not in st.session_state:
    st.session_state.selected_item = None


# ---------- Helper: Path Join ----------
def join_path(base, name):
    """Manually join paths depending on OS type (no os.path)."""
    sep = st.session_state.path_sep
    base = base.rstrip("\\/")  # remove trailing slashes
    return base + sep + name


# ---------- Helper: Get Parent Directory ----------
def get_parent_path(path):
    """Return parent directory manually based on separator."""
    sep = st.session_state.path_sep
    parts = path.rstrip(sep).split(sep)
    if len(parts) > 1:
        parent = sep.join(parts[:-1]) + sep
    else:
        parent = path
    return parent


# ---------- Function to list remote directory ----------
def list_remote_files(directory):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            REMOTE_HOST,
            username=st.session_state.remote_user,
            password=st.session_state.remote_pass
        )

        # Choose OS-appropriate command
        if st.session_state.os_type == "windows":
            cmd = f'cd "{directory}" && dir /B'
        else:
            cmd = f'cd "{directory}" && ls -1'

        stdin, stdout, stderr = ssh.exec_command(cmd)
        output = stdout.read().decode(errors="ignore").splitlines()
    finally:
        ssh.close()

    return output


# ---------- Streamlit UI ----------
st.set_page_config(page_title="Remote File Manager", layout="wide")
st.title("📂 Remote File Manager")

st.subheader("Connection Info")
st.text(f"Connected to: {st.session_state.remote_user}@{REMOTE_HOST}")
st.text(f"Current Path: {st.session_state.pwd}")

st.divider()

# ---------- Directory Navigation ----------
col_nav1, col_nav2 = st.columns([1, 6])

with col_nav1:
    if st.button("⬅️ Up"):
        parent = get_parent_path(st.session_state.pwd)
        if parent and parent != st.session_state.pwd:
            st.session_state.pwd = parent
            st.session_state.selected_item = None
            st.rerun()

with col_nav2:
    st.write("### Current Directory Listing")

# ---------- Directory Listing ----------
try:
    files = list_remote_files(st.session_state.pwd)
    sep = st.session_state.path_sep

    for f in files:
        full_path = join_path(st.session_state.pwd, f)

        if "." not in f:  # folder
            if st.button(f"📁 {f}", key=f"folder_{f}"):
                st.session_state.pwd = full_path
                st.session_state.selected_item = None
                st.rerun()
        else:  # file
            if st.button(f"📄 {f}", key=f"file_{f}"):
                st.session_state.selected_item = f
                st.success(f"Selected: {f}")

except Exception as e:
    st.error(f"Failed to list directory: {e}")

st.divider()
st.subheader("File Operations")

filename = st.text_input("Enter filename:", value=st.session_state.selected_item or "")
dest_path_input = st.text_input("Destination path (for Copy/Move):", key="dest")


# ---------- Normalize destination ----------
def resolve_destination(dest_path):
    """Resolve relative to current PWD if not absolute."""
    sep = st.session_state.path_sep
    os_type = st.session_state.os_type

    if not dest_path:
        return ""

    # Detect absolute path manually
    if os_type == "windows":
        is_abs = (":" in dest_path) or dest_path.startswith("\\")
    else:
        is_abs = dest_path.startswith("/")

    # Join manually if not absolute
    if not is_abs:
        if st.session_state.pwd.endswith(sep):
            dest_path = st.session_state.pwd + dest_path
        else:
            dest_path = st.session_state.pwd + sep + dest_path

    return dest_path


# ---------- Operation Buttons ----------
col1, col2, col3, col4 = st.columns(4)
selected = st.session_state.selected_item
disabled_ops = selected is None

with col1:
    if st.button("🟩 Create"):
        if filename:
            r = requests.post(
                f"{FLASK_BACKEND}/create",
                json={"filename": join_path(st.session_state.pwd, filename)}
            )
            st.success(f"Create Status: {r.json()}")
        else:
            st.error("Enter filename!")

with col2:
    if st.button("🗑️ Delete", disabled=disabled_ops):
        if selected:
            r = requests.delete(
                f"{FLASK_BACKEND}/delete",
                json={"filename": join_path(st.session_state.pwd, selected)}
            )
            st.success(f"Delete Status: {r.json()}")
            st.text(join_path(st.session_state.pwd, selected))
            # st.session_state.selected_item = None
            # st.rerun()

with col3:
    if st.button("📋 Copy", disabled=disabled_ops):
        if selected and dest_path_input:
            source_path = join_path(st.session_state.pwd, selected)
            destination_path = resolve_destination(dest_path_input)
            r = requests.post(
                f"{FLASK_BACKEND}/copy",
                json={"source": source_path, "destination": destination_path}
            )
            st.success(f"Copy Status: {r.json()}")
        else:
            st.error("Enter destination path!")

with col4:
    if st.button("📂 Move", disabled=disabled_ops):
        if selected and dest_path_input:
            source_path = join_path(st.session_state.pwd, selected)
            destination_path = resolve_destination(dest_path_input)
            r = requests.post(
                f"{FLASK_BACKEND}/move",
                json={"source": source_path, "destination": destination_path}
            )
            st.success(f"Move Status: {r.json()}")
            st.session_state.selected_item = None
            st.rerun()
        else:
            st.error("Enter destination path!")
