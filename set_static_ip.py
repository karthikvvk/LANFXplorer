import os
import re
import platform
import subprocess
import ipaddress
from dotenv import load_dotenv
from elevate import elevate
from scapy.all import ARP, Ether, srp
from scanner import gethostlist
import runpy


def scan_network():
    load_dotenv()
    default_ip = os.getenv("DEFAULTIP", "172.18.0.2")
    cidr = os.getenv("CIDAR", "16")
    gateway = os.getenv("GATEWAY", "172.18.0.1")
    scanner_ip = os.getenv("SCANNER", "172.18.0.200")

    subnet = f"{gateway}/{cidr}"
    print(f"[*] Using subnet from .env: {subnet}")

    system_name = platform.system().lower()

    if system_name == "linux":
        # Detect ethernet interface starting with 'e'
        result = subprocess.check_output(["ip", "a"], text=True)
        interfaces = re.findall(r'^\d+:\s+([\w\d\-\_]+):', result, re.MULTILINE)
        interface = None
        for i in interfaces:
            if i.startswith("e"):
            # if i.startswith("w"):
                interface = i
                break
        if not interface:
            raise Exception("[-] No Ethernet interface found")
        print(f"[*] Using interface: {interface}")

        # Temporarily assign scanner IP
        print(f"[*] Assigning temporary scanner IP {scanner_ip}/{cidr} to {interface}")
        subprocess.run(f"sudo ip addr flush dev {interface}", shell=True)
        subprocess.run(f"sudo ip addr add {scanner_ip}/{cidr} dev {interface}", shell=True)

        # Perform ARP scan
        print(f"[*] Running arp-scan on {subnet}")
        os.system("rm -f ips.txt")
        os.system(f"arp-scan --interface={interface} {subnet} | awk '/^[0-9]+\./{{print $1}}' >> ips.txt")

        with open("ips.txt", "r") as fh:
            lines = fh.readlines()
        unique_ips = set(line.strip() for line in lines if line.strip())

        print(f"[+] Found {len(unique_ips)} active hosts on LAN")
        if scanner_ip in unique_ips:
            unique_ips.remove(scanner_ip)
        return unique_ips, interface

    elif system_name.startswith("win"):
        # Uses PowerShell to return adapter names directly
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-NetAdapter | Select-Object -ExpandProperty Name"
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        # split and strip empty lines
        interface = [line.strip() for line in proc.stdout.splitlines() if line.strip()]

        unique_ips = gethostlist()

        return unique_ips, interface

    else:
        print("[-] Unsupported OS for scanning")
        return set(), None


def find_unused_ip(subnet, used_ips, start=10, end=250):
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
        "sudo bash -c 'echo nameserver 8.8.8.8 >> /etc/resolv.conf'"
    ]
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




elevate(show_console=False)
load_dotenv()

default_ip = os.getenv("DEFAULTIP", "172.18.0.2")
subnet_mask = os.getenv("SUBNET", "255.255.0.0")
cidr = os.getenv("CIDAR", "16")
gateway = os.getenv("GATEWAY", "172.18.0.1")
broadcast = os.getenv("BROADCAST", "172.18.0.255")

subnet = f"{gateway}/{cidr}"

print("[*] Loaded configuration from .env:")
print(f"    DEFAULTIP = {default_ip}")
print(f"    SUBNET    = {subnet}")
print(f"    MASK      = {subnet_mask}")
print(f"    GATEWAY   = {gateway}")
print(f"    BROADCAST = {broadcast}")

# --- Perform scan and get used IPs ---
used_ips, iface = scan_network()

if iface is None:
    print("[-] Could not detect Ethernet interface. Exiting.")
    

# --- Find first available IP ---
chosen_ip = find_unused_ip(subnet, used_ips)
if not chosen_ip:
    print("[-] No free IP found. Network fully allocated.")
    print("[!] Exiting: no more hosts supported.")
    

os_type = platform.system().lower()
print(f"[+] OS detected: {os_type}")
print(f"[+] Assigning IP {chosen_ip} (Gateway {gateway})")

if "linux" in os_type:
    configure_linux(iface, chosen_ip, gateway, cidr)
elif "windows" in os_type:
    configure_windows(iface, chosen_ip, subnet_mask, gateway)
else:
    print("[-] Unsupported OS type")

print(f"[✓] Successfully assigned {chosen_ip} on interface {iface}")

