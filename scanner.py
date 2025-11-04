import getpass
import os
import subprocess, platform
from dotenv import load_dotenv
import re


default_ip = ""
cidr = ""
gateway = ""
scanner_ip = ""
interface = ""
system_name = ""
user = ""
cpfiledest = ""
pwd = ""
file_path = ""

def load_env():
    global default_ip, cidr, gateway, scanner_ip, interface, system_name, user, cpfiledest, pwd
    load_dotenv()
    default_ip = os.getenv("DEFAULTIP", "172.18.0.2")
    cidr = os.getenv("CIDAR", "16")
    gateway = os.getenv("GATEWAY", "172.18.0.1")
    scanner_ip = os.getenv("SCANNER", "172.18.0.200")
    interface = os.getenv("INTERFACE", None)
    system_name = os.getenv("SYSTEM", platform.system().lower())
    user = os.getenv("USER", getpass.getuser())
    cpfiledest = os.getenv("COPYFILEPATH", None)
    pwd = os.getenv("PWD", os.getcwd())

def checkfile():
    global default_ip, cidr, gateway, scanner_ip, interface, system_name, user, cpfiledest, pwd, file_path
    if os.path.exists(file_path):
        pass
    else:
        open(file_path, "w").close()

def gethostlist():
    load_env()
    # elevate()
    global default_ip, cidr, gateway, scanner_ip, interface, system_name, user, cpfiledest, pwd, file_path
    file_path = os.path.join(os.getcwd(), "ipsn.txt")
    if system_name.startswith("lin"):
        return scanfromlinux()
    elif system_name.startswith("win") or system_name.startswith("nt"):
        return scanfromwin()

def scanfromlinux():
    global default_ip, cidr, gateway, scanner_ip, interface, system_name, user, cpfiledest, pwd, file_path
    checkfile()
    # print("inside the scanner", os.getcwd())
    subnet = f"{gateway}/{cidr}"
    result = subprocess.check_output(["nmap", "-Pn", subnet], text=True)
    # print(result, "the result from the scanner")
    unique_ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', result)
    append_host(unique_ips)
    return unique_ips

def scanfromwin():
    global default_ip, cidr, gateway, scanner_ip, interface, system_name, user, cpfiledest, pwd, file_path
    checkfile()
    result = subprocess.run(["arp", "-a"], capture_output=True, text=True)
    output = result.stdout
    ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', output)
    unique_ips = set(ips)
    append_host(unique_ips)  
    return unique_ips


def append_host(lis):
    global default_ip, cidr, gateway, scanner_ip, interface, system_name, user, cpfiledest, pwd, file_path
    checkfile()
    fh = open(file_path, "r")
    data = fh.readlines()
    fh.close()
    existing_ips = list(set(line.strip() for line in data))
    total_ips = set(existing_ips + lis)
    fh = open(file_path, "w")
    for ip in total_ips:
        fh.write(ip + "\n")
    fh.close()
    os.system(f"cp  {file_path} {cpfiledest}")
