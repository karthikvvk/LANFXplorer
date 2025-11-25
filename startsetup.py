import getpass
import os
import platform
import re, subprocess
from dotenv import set_key, load_dotenv


dirs = os.listdir()
pwd = os.getcwd()
user = getpass.getuser()
sys = platform.system().lower()
copyfilepath = os.path.join(pwd, "ipsn.txt")
interface = None
laytodir="pages"
laytofil = "2_File_Manager.py"



lis = ['.env', '1_Select_Host.py',  'server.py', 'requirement.txtt', 'scanner.py', 'startsetup.py', 'set_static_ip.py']
for i in lis:
    if i in dirs:
        pass
    else:
        print(f"Critical File {i} are not Available!!")
        exit()

if os.path.exists(os.path.join(pwd,laytodir, laytofil)):
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
            print("the iface: ", interface)
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
    for i in interface:
        u = i.lower()
        # if u.startswith("e"):
        if u.startswith("w"):
            interface = u
            # print("the iface: ", interface)
            break
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
load_dotenv(env_file)
if not os.path.exists(env_file):
    open(env_file, "a").close()
for key, value in env_vars.items():
    set_key(env_file, key, str(value))



os.system("python " + os.path.join(pwd, "set_static_ip.py"))