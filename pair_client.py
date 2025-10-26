# pair_client.py (sketch)
import subprocess
import requests
import tempfile
import os

def generate_keypair(key_path):
    subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", key_path, "-N", ""], check=True)

def send_pair_request(receiver_ip, user, key_pub_path):
    url = f"https://{receiver_ip}:8443/pair/request"
    data = {"user": user}
    files = {"pubkey": open(key_pub_path, "rb")}
    # Accept self-signed cert for initial local pairing if agent uses self-signed; but prefer proper TLS or mTLS in prod
    resp = requests.post(url, data=data, files=files, verify=False)
    return resp.json()

if __name__ == "__main__":
    keyfile = os.path.expanduser("~/.ssh/lfe_ed25519")
    generate_keypair(keyfile)
    pub = keyfile + ".pub"
    print(send_pair_request("192.168.1.23", "karthik", pub))
