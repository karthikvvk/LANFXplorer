import getpass
import os
import platform
import re, subprocess


dirs = os.listdir()
pwd = os.getcwd()
user = getpass.getuser()
sys = platform.system().lower()
copyfilepath = os.path.join(pwd, "ipsn.txt")
interface = None


lis = ['.env', '1_Select_Host.py',  'server.py', 'requirement.txtt', 'scanner.py', 'startsetup.py', 'set_static_ip.py']
for i in lis:
    if i in dirs:
        pass
    else:
        print(f"Critical File {i} are not Available!!")
        exit()

if os.path.exists(f'{pwd}/pages/2_File_Manager.py'):
    pass
else:
    print(f"Critical File {pwd}/pages/2_File_Manager.py are not Available!!")
    exit()

if sys.startswith("linux"):
    result = subprocess.check_output(["ip", "a"], text=True)
    interfaces = re.findall(r'^\d+:\s+([\w\d\-\_]+):', result, re.MULTILINE)
    interface = None
    for i in interfaces:
        # if i.startswith("e"):
        if i.startswith("w"):
            interface = i
            break
    if not interface:
        raise Exception("[-] No Ethernet interface found")
elif sys.startswith("win") or sys.startswith("nt"):
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-NetAdapter | Select-Object -ExpandProperty Name"
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    interface = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not interface:
        raise Exception("[-] No Ethernet interface found")
    



env_vars = {
    "PWD": pwd,
    "USER": user,
    "SYSTEM": sys,
    "INTERFACE": interface,
    "COPYFILEPATH": copyfilepath
}

env_file = ".env"
existing = {}
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                existing[k] = v
with open(env_file, "w") as f:
    for k, v in {**existing, **env_vars}.items():
        f.write(f"{k}={v}\n")


os.system("python " + pwd + "/set_static_ip.py")