import os
import platform
import subprocess
from elevate import elevate
import netifaces
from scapy.all import ARP, Ether, srp
from mad import gethostlist
import ipaddress

def get_subnet_from_ssh_hosts():
    ssh_hosts = gethostlist()
    if not ssh_hosts:
        print("[-] No SSH hosts found, falling back to local subnet")
        return None

    # Pick first SSH host and derive its /24 subnet
    ip = ssh_hosts[0]
    subnet = ipaddress.ip_network(f"{ip}/24", strict=False)
    print(f"[+] Using SSH host subnet: {subnet}")
    return str(subnet)

def scan_network():
    target_subnet = get_subnet_from_ssh_hosts()

    if not target_subnet:
        # Fallback to local interface subnet
        gateways = netifaces.gateways()
        iface = None
        if 'default' in gateways and netifaces.AF_INET in gateways['default']:
            iface = gateways['default'][netifaces.AF_INET][1]
        else:
            for i in netifaces.interfaces():
                addrs = netifaces.ifaddresses(i)
                if netifaces.AF_INET in addrs:
                    iface = i
                    break
        if not iface:
            raise RuntimeError("No active IPv4 interface found")

        ip_info = netifaces.ifaddresses(iface)[netifaces.AF_INET][0]
        subnet = ip_info['netmask']
        ip = ip_info['addr']
        target_subnet = f"{ip}/{subnet_to_cidr(subnet)}"
        print(f"[+] Fallback subnet: {target_subnet}")
    else:
        iface = None  # Let OS pick default adapter during config

    # ARP scan
    arp = ARP(pdst=target_subnet)
    ether = Ether(dst="ff:ff:ff:ff:ff:ff")
    packet = ether/arp
    result = srp(packet, timeout=2, verbose=0)[0]

    used_ips = {rcv.psrc for _, rcv in result}
    return target_subnet, used_ips, iface



def subnet_to_cidr(mask):
    return sum(bin(int(x)).count('1') for x in mask.split('.'))

def find_unused_ip(cidr, used_ips):
    base_ip = cidr.split('/')[0].rsplit('.', 1)[0]
    for i in range(100, 200):
        candidate = f"{base_ip}.{i}"
        if candidate not in used_ips:
            print(f"[+] Found unused IP: {candidate}")
            return candidate
    raise Exception("No unused IP found in range")

def configure_windows(adapter, ip):
    cmds = [
        f'netsh interface ip set address name="{adapter}" static {ip} 255.255.255.0 192.168.0.1',
        f'netsh interface ip set dns name="{adapter}" static 1.1.1.1',
        f'netsh interface ip add dns name="{adapter}" 8.8.8.8 index=2'
    ]
    for cmd in cmds:
        subprocess.run(cmd, shell=True)

def configure_linux(adapter, ip):
    cmds = [
        f'sudo ip addr flush dev {adapter}',
        f'sudo ip addr add {ip}/24 dev {adapter}',
        f'sudo ip route add default via 192.168.0.1',
        f'sudo bash -c \'echo "nameserver 1.1.1.1" > /etc/resolv.conf\'',
        f'sudo bash -c \'echo "nameserver 8.8.8.8" >> /etc/resolv.conf\'',
        f'sudo resolvectl dns {adapter} 1.1.1.1 8.8.8.8'
    ]
    for cmd in cmds:
        subprocess.run(cmd, shell=True)

def main():
    elevate(show_console=False)
    print("[*] Available interfaces:", netifaces.interfaces())
    cidr, used_ips, adapter = scan_network()
    unused_ip = find_unused_ip(cidr, used_ips)
    os_type = platform.system()

    print(f"[+] Detected OS: {os_type}")
    print(f"[+] Using adapter: {adapter}")

    if os_type == "Windows":
        configure_windows(adapter, unused_ip)
    elif os_type == "Linux":
        configure_linux(adapter, unused_ip)
    else:
        print("[-] Unsupported OS")

if __name__ == "__main__":
    main()
