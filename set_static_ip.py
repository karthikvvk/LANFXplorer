"""
LANFXplorer Static IP Assignment

Simple fallback: "you don't have an IP — I'll give you one."

Called automatically by startsetup.py when no network IP is detected.
Scans for used IPs on the interface, picks an unused one, and configures it.

Supports: Linux, Windows (including 32-bit headless).
"""

import os
import subprocess
import ipaddress
import platform

from dotenv import set_key
from app_config import get_config, reload_config


def _scan_used_ips(interface, subnet, scanner_ip, cidr, system_type):
    """
    Temporarily assign a scanner IP, then broadcast-scan for existing hosts.
    Returns a set of IP strings found on the network.
    """
    print(f"[static-ip] Scanning subnet {subnet} for used addresses...")

    if system_type.startswith("linux"):
        print(f"[static-ip] Assigning temp scanner IP {scanner_ip}/{cidr} on {interface}")
        subprocess.run(f"sudo ip addr flush dev {interface}", shell=True)
        subprocess.run(f"sudo ip addr add {scanner_ip}/{cidr} dev {interface}", shell=True)

        # Quick ARP / ping sweep to find who's alive
        used = set()
        net = ipaddress.ip_network(f"{subnet}/{cidr}", strict=False)
        base = str(list(net.hosts())[0]).rsplit(".", 1)[0]
        for i in range(1, 255):
            candidate = f"{base}.{i}"
            ret = subprocess.run(
                ["ping", "-c", "1", "-W", "1", candidate],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if ret.returncode == 0:
                used.add(candidate)
        return used

    elif system_type.startswith("win"):
        print(f"[static-ip] Assigning temp scanner IP {scanner_ip}/{cidr} on {interface}")
        subprocess.run([
            "powershell", "-Command",
            f"Get-NetIPAddress -InterfaceAlias '{interface}' -AddressFamily IPv4 "
            f"| Remove-NetIPAddress -Confirm:$false"
        ], check=False)
        subprocess.run([
            "powershell", "-Command",
            f"New-NetIPAddress -InterfaceAlias '{interface}' "
            f"-IPAddress '{scanner_ip}' -PrefixLength {cidr}"
        ], check=True)

        used = set()
        net = ipaddress.ip_network(f"{subnet}/{cidr}", strict=False)
        base = str(list(net.hosts())[0]).rsplit(".", 1)[0]
        for i in range(1, 255):
            candidate = f"{base}.{i}"
            ret = subprocess.run(
                ["ping", "-n", "1", "-w", "1000", candidate],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if ret.returncode == 0:
                used.add(candidate)
        return used

    else:
        print(f"[static-ip] Unsupported OS: {system_type}")
        return set()


def _find_unused_ip(gateway, cidr, used_ips, start=10, end=250):
    """Pick the first unused IP in the subnet range."""
    net = ipaddress.ip_network(f"{gateway}/{cidr}", strict=False)
    base = str(list(net.hosts())[0]).rsplit(".", 1)[0]
    for i in range(start, end):
        candidate = f"{base}.{i}"
        if candidate not in used_ips:
            print(f"[static-ip] Found unused IP: {candidate}")
            return candidate
    return None


def _configure_linux(adapter, ip, gateway, cidr):
    """Apply static IP config on Linux."""
    cmds = [
        f"sudo ip addr flush dev {adapter}",
        f"sudo ip addr add {ip}/{cidr} dev {adapter}",
        f"sudo ip route add default via {gateway} || true",
        "sudo bash -c 'echo nameserver 1.1.1.1 > /etc/resolv.conf'",
        "sudo bash -c 'echo nameserver 8.8.8.8 >> /etc/resolv.conf'",
    ]
    for cmd in cmds:
        print(f"[static-ip] {cmd}")
        subprocess.run(cmd, shell=True)


def _configure_windows(adapter, ip, subnet_mask, gateway):
    """Apply static IP config on Windows."""
    if not adapter:
        adapter = "Ethernet"
    cmds = [
        f'netsh interface ip set address name="{adapter}" static {ip} {subnet_mask} {gateway} 1',
        f'netsh interface ip set dns name="{adapter}" static 1.1.1.1',
        f'netsh interface ip add dns name="{adapter}" 8.8.8.8 index=2',
    ]
    for cmd in cmds:
        print(f"[static-ip] {cmd}")
        subprocess.run(cmd, shell=True)


def assign_static_ip(interface_override=None):
    """
    Main entry point.  Called when the normal startup can't find a network IP.

    1. Read config from AppConfig (gateway, cidr, subnet, etc.)
    2. Scan for used IPs on the interface
    3. Pick an unused one
    4. Configure the interface
    5. Write the chosen IP as HOST in .env

    Args:
        interface_override: If provided, use this interface instead of the one
                            from AppConfig (useful when detect_interface()
                            already found the right adapter).

    Returns:
        The assigned IP string, or None on failure.
    """
    config = get_config()

    system_type = config.system_type or platform.system().lower()
    iface = interface_override or config.interface
    gateway = config.gateway or "172.18.0.1"
    cidr = config.cidr or "16"
    subnet_mask = config.subnet or "255.255.0.0"
    scanner_ip = "172.18.0.200"  # temp IP used only during the scan
    pwd = config.pwd or os.getcwd()

    if not iface:
        print("[static-ip] No interface available — cannot assign IP.")
        return None

    print(f"[static-ip] Interface : {iface}")
    print(f"[static-ip] Gateway   : {gateway}")
    print(f"[static-ip] CIDR      : {cidr}")

    # -- scan --
    used_ips = _scan_used_ips(iface, gateway, scanner_ip, cidr, system_type)
    used_ips.discard(scanner_ip)
    print(f"[static-ip] Found {len(used_ips)} active hosts")

    # -- pick --
    chosen_ip = _find_unused_ip(gateway, cidr, used_ips)
    if not chosen_ip:
        print("[static-ip] No free IP found in subnet.")
        return None

    # -- configure --
    print(f"[static-ip] Assigning {chosen_ip} on {iface}")
    if system_type.startswith("linux"):
        _configure_linux(iface, chosen_ip, gateway, cidr)
    elif system_type.startswith("win"):
        _configure_windows(iface, chosen_ip, subnet_mask, gateway)
    else:
        print(f"[static-ip] Unsupported OS: {system_type}")
        return None

    # -- persist to .env as HOST --
    env_path = os.path.join(pwd, ".env")
    set_key(env_path, "HOST", chosen_ip)
    reload_config()

    print(f"[static-ip] ✓ Assigned {chosen_ip} on {iface}")
    return chosen_ip


# Allow standalone testing:  python set_static_ip.py
if __name__ == "__main__":
    result = assign_static_ip()
    if result:
        print(f"[static-ip] Done — HOST={result}")
    else:
        print("[static-ip] Failed to assign a static IP.")