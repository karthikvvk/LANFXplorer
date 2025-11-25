import os, time
import re
import platform
import subprocess
import ipaddress
from dotenv import load_dotenv, set_key
from elevate import elevate
from scanner import *



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
subnet_mask = ""
broadcast = ""
subnet = ""

def load_env():
    global default_ip, cidr, gateway, scanner_ip, interface, system_name, user, cpfiledest, pwd, subnet_mask, broadcast, subnet
    load_dotenv()
    default_ip = os.getenv("DEFAULTIP", "172.18.0.2")
    cidr = os.getenv("CIDAR", "16")
    gateway = os.getenv("GATEWAY", "172.18.0.1")
    subnet_mask = os.getenv("SUBNET")
    broadcast = os.getenv("BROADCAST")
    scanner_ip = os.getenv("SCANNER", "172.18.0.200")
    interface = os.getenv("INTERFACE", None)
    system_name = os.getenv("SYSTEM", platform.system().lower())
    user = os.getenv("USER", getpass.getuser())
    cpfiledest = os.getenv("COPYFILEPATH", None)
    pwd = os.getenv("PWD", os.getcwd())
    subnet = f"{gateway}/{cidr}"



def scan_network():
    global default_ip, cidr, gateway, scanner_ip, interface, system_name, user, cpfiledest, pwd, subnet_mask, broadcast, subnet
    
    print(f"[*] Using subnet from .env: {subnet}")
    if system_name == "linux":        
        print(f"[*] Using interface: {interface}")
        print(f"[*] Assigning temporary scanner IP {scanner_ip}/{cidr} to {interface}")
        subprocess.run(f"sudo ip addr flush dev {interface}", shell=True)
        subprocess.run(f"sudo ip addr add {scanner_ip}/{cidr} dev {interface}", shell=True)
        print("Assigned Temp IP:")
        set_key(os.path.join(pwd, ".env"), "CHOOSENIP", scanner_ip)
        os.system("ip a")
        print("Scanning hots in network. Pls wait this will take 1-2 min")
        unique_ips = gethostlist()
        print(f"[+] Found {len(unique_ips)} active hosts on LAN")
        # print(unique_ips, "unique ips")
        if scanner_ip in unique_ips:
            unique_ips.remove(scanner_ip)
        return unique_ips, interface
    elif system_name.startswith("win"):
        print(f"[*] Using interface: {interface}")
        print(f"[*] Assigning temporary scanner IP {scanner_ip}/{cidr} to {interface}")
        subprocess.run([
            "powershell", "-Command",
            f"Get-NetIPAddress -InterfaceAlias '{interface}' -AddressFamily IPv4 | Remove-NetIPAddress -Confirm:$false"
        ], check=False)
        subprocess.run([
            "powershell", "-Command",
            f"New-NetIPAddress -InterfaceAlias '{interface}' -IPAddress '{scanner_ip}' -PrefixLength {cidr}"
        ], check=True)
        print("Assigned Temp IP:")
        set_key(os.path.join(pwd, ".env"), "CHOOSENIP", scanner_ip)
        os.system("ipconfig")
        unique_ips = gethostlist()
        print("Scanning hots in network. Pls wait this will take 1-2 min")
        print(f"[+] Found {len(unique_ips)} active hosts on LAN")
        return unique_ips, interface
    else:
        print("[-] Unsupported OS for scanning! Sry")
        return set(), None


def find_unused_ip(subnet, used_ips, start=10, end=250):
    global default_ip, cidr, gateway, scanner_ip, interface, system_name, user, cpfiledest, pwd, subnet_mask, broadcast
    net = ipaddress.ip_network(subnet, strict=False)
    base = str(list(net.hosts())[0]).rsplit(".", 1)[0]
    for i in range(start, end):
        candidate = f"{base}.{i}"
        if candidate not in used_ips:
            print(f"[+] Found unused IP: {candidate}")
            return candidate
    return None


def configure_linux(adapter, ip, gateway, cidr):
    cmds = [
        f"sudo ip addr flush dev {adapter}",
        f"sudo ip addr add {ip}/{cidr} dev {adapter}",
        f"sudo ip route add default via {gateway} || true",
        "sudo bash -c 'echo nameserver 1.1.1.1 > /etc/resolv.conf'",
        "sudo bash -c 'echo nameserver 8.8.8.8 >> /etc/resolv.conf'"]
    for cmd in cmds:
        print("[*]", cmd)
        subprocess.run(cmd, shell=True)


def configure_windows(adapter, ip, netmask, gateway):
    if not adapter:
        adapter = "Ethernet"
    cmds = [
        f'netsh interface ip set address name="{adapter}" static {ip} {netmask} {gateway} 1',
        f'netsh interface ip set dns name="{adapter}" static 1.1.1.1',
        f'netsh interface ip add dns name="{adapter}" 8.8.8.8 index=2'
    ]
    for cmd in cmds:
        print("[*]", cmd)
        subprocess.run(cmd, shell=True)




elevate(graphical=False, show_console=False)
load_env()
print("[*] Loaded configuration from .env:")
print(f"    DEFAULTIP = {default_ip}")
print(f"    SUBNET    = {subnet}")
print(f"    MASK      = {subnet_mask}")
print(f"    GATEWAY   = {gateway}")
print(f"    BROADCAST = {broadcast}")

used_ips, iface = scan_network()

if iface is None:
    print("[-] Could not detect Ethernet interface. Exiting.")
# print(subnet.split("/")[0], used_ips)
chosen_ip = find_unused_ip(subnet.split("/")[0], used_ips)

if not chosen_ip:
    print("[-] No free IP found. Network fully allocated.")
    print("[!] Exiting: no more hosts supported.")
print(f"[+] OS detected: {system_name}")
print(f"[+] Assigning IP {chosen_ip} (Gateway {gateway})")
if "linux" in system_name:
    configure_linux(iface, chosen_ip, gateway, cidr)
elif "windows" in system_name:
    configure_windows(iface, chosen_ip, subnet_mask, gateway)
else:
    print("[-] Unsupported OS type")
# time.sleep(50)

set_key(os.path.join(pwd, ".env"), "CHOOSENIP", chosen_ip)
print("choosen ip set in env")
print(f"[✓] Successfully assigned {chosen_ip} on interface {iface}")