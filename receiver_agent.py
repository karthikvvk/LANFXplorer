# receiver_agent.py (sketch)
from fastapi import FastAPI, UploadFile, Form
import os, shutil, uuid, subprocess

app = FastAPI()
PENDING = {}

@app.post("/pair/request")
async def pair_request(user: str = Form(...), pubkey: UploadFile = None):
    content = await pubkey.read()
    token = str(uuid.uuid4())
    # store pending request
    PENDING[token] = {"user": user, "pubkey": content.decode(), "ip": None}
    # notify local UI (e.g., via websocket or polling)
    return {"token": token, "status": "pending"}

@app.post("/pair/accept")
async def pair_accept(token: str = Form(...)):
    req = PENDING.get(token)
    if not req:
        return {"error": "invalid token"}
    # append with restrictions
    home = os.path.expanduser("~")
    sshdir = os.path.join(home, ".ssh")
    os.makedirs(sshdir, exist_ok=True, mode=0o700)
    auth_file = os.path.join(sshdir, "authorized_keys")
    line = f'no-pty,no-agent-forwarding,command="/usr/local/bin/lim_file_ops" {req["pubkey"].strip()}\n'
    with open(auth_file, "a") as f:
        f.write(line)
    os.chmod(auth_file, 0o600)
    del PENDING[token]
    return {"status": "accepted"}
