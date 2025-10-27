import streamlit as st
import requests
import json
from pathlib import Path
import subprocess


st.set_page_config(page_title="Select Host", layout="centered")

try:
    # Run the command in the shell
    result = subprocess.run(
        "ip route get 1.1.1.1 | awk '{print $7; exit}'",
        capture_output=True,
        text=True,
        shell=True  # important for pipelines
    )
    ip = result.stdout.strip()
except Exception as e:
    pass
try:
    # Run ipconfig and capture output
    result = subprocess.run(["ipconfig"], capture_output=True, text=True)
    # Iterate over lines containing 'IPv4'
    for line in result.stdout.splitlines():
        if "IPv4" in line:
            # Split by spaces/dots and take last 4 parts
            ip_parts = line.split()[-1].split(".")[-4:]
            ip = ".".join(ip_parts)
            # print(ip)
except:
    pass

FLASK_BACKEND = "http://" + ip + ":5000"
print(FLASK_BACKEND)
st.session_state.ip = FLASK_BACKEND
st.title("🌐 Network Hosts")
st.write("Select a host to connect:")

# ---------- Caching the host list ----------
@st.cache_data(show_spinner=True)
def get_host_list():
    try:
        response = requests.get(f"{FLASK_BACKEND}/lsithost", timeout=100)
        return response.json()
    except Exception as e:
        st.error(f"Failed to fetch host list: {e}")
        return []

# Only call API once per session
if "host_data" not in st.session_state:
    st.session_state.host_data = get_host_list()

host_data = st.session_state.host_data

if not host_data:
    st.warning("No hosts found.")
    st.stop()

# ---------- Render host buttons ----------
selected_host = st.session_state.get("selected_host")

cols = st.columns(3)
for i, h in enumerate(host_data):
    host_ip = h.get("host")
    os_type = h.get("os", "unknown")
    user = h.get("user", "unknown")

    if cols[i % 3].button(f"{user}@{host_ip} ({os_type})", key=host_ip):
        st.session_state.selected_host = host_ip
        st.session_state.selected_os = os_type
        st.session_state.remote_user = user
        st.session_state.password_prompt = True





# ---------- Password prompt ----------
if st.session_state.get("password_prompt", False):
    st.divider()
    st.write(f"🔐 Enter password for **{st.session_state.remote_user}@{st.session_state.selected_host}**")
    pwd = st.text_input("Password", type="password", key="pass_input")

    if st.button("Connect", type="primary"):
        st.session_state.remote_pass = pwd
        st.session_state.REMOTE_HOST = st.session_state.selected_host

        # # ---------- Backend handshake ----------
        # try:
        #     r = requests.get(f"{FLASK_BACKEND}/connect", timeout=10)
        #     data = r.json()
        #     st.session_state.remote_user = data.get("user", st.session_state.remote_user)
        #     st.session_state.os_type = data.get("os", st.session_state.selected_os)
        # except Exception as e:
        #     st.warning(f"Backend connection check failed: {e}")

        # ---------- Save connection info to JSON ----------
        save_file = Path("host_list.json")
        all_data = []

        # Load old data if present
        if save_file.exists():
            try:
                with open(save_file, "r") as f:
                    all_data = json.load(f)
            except json.JSONDecodeError:
                all_data = []  # reset on corruption

        # Prepare record
        new_entry = {
            "ip": st.session_state.selected_host,
            "username": st.session_state.remote_user,
            "password": st.session_state.remote_pass,
            "os_type": st.session_state.selected_os,
        }

        # Update or append
        found = False
        for entry in all_data:
            if entry.get("ip") == new_entry["ip"]:
                entry.update(new_entry)
                found = True
                break
        if not found:
            all_data.append(new_entry)

        # Write back
        with open(save_file, "w") as f:
            json.dump(all_data, f, indent=4)

        # ---------- Continue workflow ----------
        st.session_state.password_prompt = False
        requests.get(f"{FLASK_BACKEND}/connect")
        st.switch_page("pages/2_File_Manager.py")

