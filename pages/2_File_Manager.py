import streamlit as st
import paramiko
import requests
import os
import tkinter as tk
from tkinter import filedialog
import multiprocessing

if "REMOTE_HOST" not in st.session_state:
    st.warning("Please select a host first.")
    st.switch_page("pages/1_Select_Host.py")

REMOTE_HOST = st.session_state.REMOTE_HOST
REMOTE_PASS = st.session_state.remote_pass
FLASK_BACKEND = st.session_state.ip
os_type = st.session_state.selected_os
username = st.session_state.remote_user


if "pwd" not in st.session_state:
    if os_type == "windows":
        st.session_state.pwd = f"C:\\Users\\{username}\\"
        st.session_state.path_sep = "\\"
    else:
        st.session_state.pwd = f"/home/{username}/"
        st.session_state.path_sep = "/"
if "path_sep" not in st.session_state:
    if "selected_os" in st.session_state:
        st.session_state.path_sep = "\\" if st.session_state.selected_os == "windows" else "/"
    else:
        st.session_state.path_sep = "/"

if "selected_item" not in st.session_state:
    st.session_state.selected_item = None




def join_path(base, name):

    sep = st.session_state.path_sep
    base = base.rstrip("\\/")
    return base + sep + name


def get_parent_path(path):
    sep = st.session_state.path_sep
    parts = path.rstrip(sep).split(sep)
    if len(parts) > 1:
        parent = sep.join(parts[:-1]) + sep
    else:
        parent = path
    return parent


def list_remote_files(directory):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            REMOTE_HOST,
            username=st.session_state.remote_user,
            password=st.session_state.remote_pass
        )
        if st.session_state.selected_os == "windows":
            cmd = f'cd "{directory}" && dir /B'
        else:
            cmd = f'cd "{directory}" && ls -1'
        stdin, stdout, stderr = ssh.exec_command(cmd)
        output = stdout.read().decode(errors="ignore").splitlines()
    finally:
        ssh.close()

    return output


st.set_page_config(page_title="Remote File Manager", layout="wide")
st.title("📂 Remote File Manager")
st.subheader("Connection Info")
st.text(f"Connected to: {st.session_state.remote_user}@{REMOTE_HOST}")
st.text(f"Current Path: {st.session_state.pwd}")
st.divider()
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
try:
    files = list_remote_files(st.session_state.pwd)
    sep = st.session_state.path_sep

    for f in files:
        full_path = join_path(st.session_state.pwd, f)

        if "." not in f:
            if st.button(f"📁 {f}", key=f"folder_{f}"):
                st.session_state.pwd = full_path
                st.session_state.selected_item = None
                st.rerun()
        else:
            if st.button(f"📄 {f}", key=f"file_{f}"):
                st.session_state.selected_item = f
                st.success(f"Selected: {f}")

except Exception as e:
    st.error(f"Failed to list directory: {e}")

st.divider()
st.subheader("File Operations")
filename = st.text_input("Enter filename:", value=st.session_state.selected_item or "")
dest_path_input = st.text_input("Destination path (for Copy/Move):", key="dest")


def resolve_destination(dest_path):
    sep = st.session_state.path_sep
    os_type = st.session_state.selected_os

    if not dest_path:
        return ""

    if os_type == "windows":
        is_abs = (":" in dest_path) or dest_path.startswith("\\")
    else:
        is_abs = dest_path.startswith("/")

    if not is_abs:
        if st.session_state.pwd.endswith(sep):
            dest_path = st.session_state.pwd + dest_path
        else:
            dest_path = st.session_state.pwd + sep + dest_path

    return dest_path


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










st.divider()
st.subheader("💾 Copy to This PC")
if selected:
    source_path = join_path(st.session_state.pwd, selected)
    st.text(f"Selected Remote File: {source_path}")
    is_folder = False
else:
    source_path = st.session_state.pwd.rstrip(st.session_state.path_sep)
    st.text(f"Selected Remote Folder: {source_path}")
    is_folder = True





def pick_local_folder():
    try:
        resp = requests.get(f"{FLASK_BACKEND}/selectdest", timeout=120)
        data = resp.json()
        return data.get("selected")
    except Exception as e:
        st.error(f"Failed to select destination: {e}")
        return None



if st.button("📥 Copy to This PC"):
    local_dest = pick_local_folder()
    if not local_dest:
        st.warning("❌ No destination folder selected.")
    else:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            REMOTE_HOST,
            username=st.session_state.remote_user,
            password=st.session_state.remote_pass
        )

        local_target = os.path.join(local_dest, os.path.basename(source_path))

        try:
            if is_folder and not os.path.exists(local_target):
                os.makedirs(local_target, exist_ok=True)

            if st.session_state.selected_os == "windows":
                if is_folder:
                    cmd = (
                        f"powershell -Command "
                        f"Get-ChildItem -Path '{source_path}' -Recurse -File | "
                        f"ForEach-Object {{ Get-Content $_.FullName -Encoding Byte }} "
                    )
                else:
                    cmd = f"type \"{source_path}\""
            else:
                if is_folder:
                    cmd = f"tar -cf - -C \"{os.path.dirname(source_path)}\" \"{os.path.basename(source_path)}\""
                else:
                    cmd = f"cat \"{source_path}\""

            stdin, stdout, stderr = ssh.exec_command(cmd)

            if is_folder:
                if st.session_state.selected_os == "windows":
                    st.error("⚠️ Recursive folder streaming is not supported natively on Windows SSH yet.")
                else:
                    import tarfile
                    import io
                    tar_stream = io.BytesIO(stdout.read())
                    with tarfile.open(fileobj=tar_stream) as tar:
                        tar.extractall(local_dest)
                    st.success(f"✅ Folder copied successfully:\n{source_path} → {local_target}")
            else:
                with open(local_target, "wb") as f:
                    for chunk in iter(lambda: stdout.read(4096), b""):
                        f.write(chunk)

                exit_status = stdout.channel.recv_exit_status()
                if exit_status == 0:
                    st.success(f"✅ File copied successfully:\n{source_path} → {local_target}")
                else:
                    err = stderr.read().decode(errors="ignore")
                    st.error(f"⚠️ SSH copy failed ({exit_status}): {err}")

        except Exception as e:
            st.error(f"⚠️ Failed to copy: {e}")

        finally:
            ssh.close()




st.divider()
st.subheader("📤 Copy from This PC")

uploaded_file = st.file_uploader("Select file", type=None, label_visibility="collapsed")

if uploaded_file is not None:
    st.success(f"Selected: {uploaded_file.name}")
    st.text(f"Current Remote Path: {st.session_state.pwd}")

    if st.button("📤 Copy to Remote"):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(REMOTE_HOST, username=username, password=REMOTE_PASS)

            sftp = ssh.open_sftp()
            remote_dest = join_path(st.session_state.pwd, uploaded_file.name)
            with sftp.file(remote_dest, "wb") as f:
                f.write(uploaded_file.getbuffer())
            sftp.close()
            ssh.close()
            st.success(f"✅ Uploaded {uploaded_file.name} → {remote_dest}")
        except Exception as e:
            st.error(f"Upload failed: {e}")