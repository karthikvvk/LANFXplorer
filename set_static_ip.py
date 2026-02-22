"""
LANFXplorer Static IP Assignment — Simple Ping-Scan

Fallback for direct-cable Ethernet P2P: assigns a unique static IP by
ping-scanning the 192.168.0.x/24 subnet and picking the first IP that
nobody responds to.

Flow:
  1. Guard: only runs for Ethernet interfaces (eth/enp/ens/en), NOT wlan/wl.
  2. Bring interface up with a temp IP so we can ping the subnet.
  3. Ping-scan 192.168.0.2–254 concurrently.
  4. First IP with no reply → assign it permanently.

Called automatically by startsetup.py when no network IP is detected.
Supports: Linux, Windows (including 32-bit headless).
"""

import os
import subprocess
import platform
import concurrent.futures

from dotenv import set_key
from app_config import get_config, reload_config


# ─── Constants ──────────────────────────────────────────────────────
GATEWAY     = "192.168.0.1"
CIDR        = "24"
SUBNET_MASK = "255.255.255.0"
BROADCAST   = "192.168.0.255"
TEMP_IP     = "192.168.0.200"          # used only to bring the link up
IP_RANGE    = range(2, 255)            # .2 through .254


# ─── Helpers ────────────────────────────────────────────────────────

def _is_ethernet(interface: str) -> bool:
    """Return True only for wired Ethernet interfaces."""
    low = interface.lower()
    # Ethernet prefixes on Linux: eth*, enp*, ens*, eno*, en*
    # Windows: "ethernet", "lan", …
    # Explicitly reject wireless prefixes
    if low.startswith(("wlan", "wl", "wlp")):
        return False
    if low.startswith(("eth", "enp", "ens", "eno", "en", "lan")):
        return True
    # On Windows the name may be "Ethernet", "Ethernet 2", etc.
    if "ethernet" in low or "lan" in low:
        return True
    return False


def _ping_ok(ip: str, system_type: str) -> bool:
    """Return True if *ip* responds to a single ping."""
    try:
        if system_type.startswith("win"):
            cmd = ["ping", "-n", "1", "-w", "500", ip]
        else:
            cmd = ["ping", "-c", "1", "-W", "1", ip]
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=3)
        return r.returncode == 0
    except Exception:
        return False


def _find_free_ip(system_type: str) -> str | None:
    """Ping-scan the subnet and return the first IP that does NOT reply."""
    ips = [f"192.168.0.{i}" for i in IP_RANGE if f"192.168.0.{i}" != TEMP_IP]

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
        futures = {pool.submit(_ping_ok, ip, system_type): ip for ip in ips}
        for future in concurrent.futures.as_completed(futures):
            ip = futures[future]
            if not future.result():        # no reply → it's free
                # Cancel remaining work so we don't wait
                pool.shutdown(wait=False, cancel_futures=True)
                return ip
    return None


# ─── Interface bring-up ────────────────────────────────────────────

def _bring_up_linux(interface: str):
    """Assign a temp IP on Linux so the interface can send pings."""
    subprocess.run(f"sudo ip addr flush dev {interface}",
                   shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(f"sudo ip addr add {TEMP_IP}/{CIDR} dev {interface}",
                   shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(f"sudo ip link set dev {interface} up",
                   shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _bring_up_windows(interface: str):
    subprocess.run([
        "powershell", "-Command",
        f"Get-NetIPAddress -InterfaceAlias '{interface}' -AddressFamily IPv4 "
        f"| Remove-NetIPAddress -Confirm:$false"
    ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([
        "powershell", "-Command",
        f"New-NetIPAddress -InterfaceAlias '{interface}' "
        f"-IPAddress '{TEMP_IP}' -PrefixLength {CIDR}"
    ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ─── Final configuration ───────────────────────────────────────────

def _configure_linux(adapter, ip):
    cmds = [
        f"sudo ip addr flush dev {adapter}",
        f"sudo ip addr add {ip}/{CIDR} dev {adapter}",
        f"sudo ip link set dev {adapter} up",
    ]
    for cmd in cmds:
        print(f"[static-ip] {cmd}")
        subprocess.run(cmd, shell=True)


def _configure_windows(adapter, ip):
    if not adapter:
        adapter = "Ethernet"
    cmds = [
        f'netsh interface ip set address name="{adapter}" static {ip} {SUBNET_MASK} {GATEWAY} 1',
        f'netsh interface ip set dns name="{adapter}" static 1.1.1.1',
        f'netsh interface ip add dns name="{adapter}" 8.8.8.8 index=2',
    ]
    for cmd in cmds:
        print(f"[static-ip] {cmd}")
        subprocess.run(cmd, shell=True)


# ─── Main entry point ──────────────────────────────────────────────

def assign_static_ip(interface_override=None):
    """
    Assign a static IP on an Ethernet interface that has no address.

    Ping-scans 192.168.0.2–254 and takes the first IP nobody replies to.
    Only works for Ethernet (eth/enp/ens/en) — silently skips WLAN.

    Returns the assigned IP string, or None on failure / skip.
    """
    config = get_config()
    system_type = config.system_type or platform.system().lower()
    iface = interface_override or config.interface

    if not iface:
        print("[static-ip] No interface available — cannot assign IP.")
        return None

    # ── Guard: Ethernet only ──
    if not _is_ethernet(iface):
        print(f"[static-ip] {iface} is not Ethernet — skipping static IP.")
        return None

    print(f"[static-ip] Interface : {iface}")
    print(f"[static-ip] Gateway   : {GATEWAY}")
    print(f"[static-ip] Subnet    : 192.168.0.0/{CIDR}")

    # Step 1: bring up the interface with a temp IP
    print(f"[static-ip] Bringing up {iface} with temp IP {TEMP_IP}/{CIDR}")
    if system_type.startswith("linux"):
        _bring_up_linux(iface)
    elif system_type.startswith("win"):
        _bring_up_windows(iface)
    else:
        print(f"[static-ip] Unsupported OS: {system_type}")
        return None

    # Step 2: ping-scan to find a free IP
    print("[static-ip] Scanning subnet for a free IP...")
    free_ip = _find_free_ip(system_type)

    if not free_ip:
        print("[static-ip] All IPs in 192.168.0.2–254 responded — none free!")
        return None

    # Step 3: configure the chosen IP
    print(f"[static-ip] Found free IP: {free_ip} — assigning on {iface}")
    if system_type.startswith("linux"):
        _configure_linux(iface, free_ip)
    elif system_type.startswith("win"):
        _configure_windows(iface, free_ip)

    # Step 4: persist to .env
    pwd = config.pwd or os.getcwd()
    env_path = os.path.join(pwd, ".env")
    set_key(env_path, "HOST", free_ip)
    reload_config()

    print(f"[static-ip] ✓ Assigned {free_ip} on {iface}")
    return free_ip


# Allow standalone testing:  python set_static_ip.py
if __name__ == "__main__":
    result = assign_static_ip()
    if result:
        print(f"[static-ip] Done — HOST={result}")
    else:
        print("[static-ip] Failed or skipped.")