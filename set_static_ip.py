"""
LANFXplorer Static IP Assignment — Simple Ping-Scan

Fallback for direct-cable Ethernet P2P: assigns a unique static IP by
ping-scanning the 192.168.0.x/24 subnet and picking the first IP that
nobody responds to.

Flow:
  1. Guard: only runs for Ethernet interfaces (eth/enp/ens/en), NOT wlan/wl.
  2. Bring interface up with a temp IP so we can ping the subnet.
  3. Ping 192.168.0.2, .3, .4 … in order — first non-responding IP is taken.
  4. First free IP → assign it permanently.

Called automatically by startsetup.py when no network IP is detected.
Supports: Linux, Windows (including 32-bit headless).
"""

import os
import subprocess
import platform

from app_config import get_config, reload_config


# ─── Constants ──────────────────────────────────────────────────────
GATEWAY     = "192.168.0.1"
CIDR        = "24"
SUBNET_MASK = "255.255.255.0"
BROADCAST   = "192.168.0.255"
# NOTE: TEMP_IP is in the 192.168.224.x subnet — a completely different range from
# the 192.168.0.x range we assign into.  This ensures the temp address never
# appears as a "free" candidate and cannot conflict with the peer's scan.
TEMP_IP     = "192.168.0.223"       # used only to bring the link up
TEMP_CIDR   = "24"                    # /24 for the temp subnet
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
    """
    Probe IPs in sequential order (.2, .3, .4 …) and return the first one
    that does NOT reply to a ping.

    Sequential order is critical for collision avoidance in Ethernet P2P:
      - Peer A starts first → pings .2, no reply → takes .2, brings it up.
      - Peer B starts later → pings .2, gets a reply from A → skips to .3.
    A concurrent/random scan would cause both peers to race and both claim .2.
    """
    for i in IP_RANGE:
        ip = f"192.168.0.{i}"
        if ip == TEMP_IP:          # skip the temp address (different subnet anyway)
            continue
        alive = _ping_ok(ip, system_type)
        print(f"[static-ip]   ping {ip} → {'alive (skip)' if alive else 'free  ✓'}")
        if not alive:
            return ip              # nobody answered → take it
    return None


# ─── Interface bring-up ────────────────────────────────────────────

def _bring_up_linux(interface: str):
    """Assign a temp IP on Linux so the interface can send pings."""
    subprocess.run(f"sudo ip addr flush dev {interface}",
                   shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Use TEMP_CIDR (temp subnet /24) — TEMP_IP is in 192.168.224.x
    subprocess.run(f"sudo ip addr add {TEMP_IP}/{TEMP_CIDR} dev {interface}",
                   shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(f"sudo ip link set dev {interface} up",
                   shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _bring_up_windows(interface: str):
    subprocess.run([
        "powershell", "-Command",
        f"Get-NetIPAddress -InterfaceAlias '{interface}' -AddressFamily IPv4 "
        f"| Remove-NetIPAddress -Confirm:$false"
    ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Use TEMP_CIDR for the temp subnet (192.168.224.x)
    subprocess.run([
        "powershell", "-Command",
        f"New-NetIPAddress -InterfaceAlias '{interface}' "
        f"-IPAddress '{TEMP_IP}' -PrefixLength {TEMP_CIDR}"
    ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ─── Final configuration ───────────────────────────────────────────

def _configure_linux(adapter, ip):
    """
    Assign *ip* permanently on *adapter* via a NetworkManager connection profile.

    Why nmcli instead of raw `ip addr`:
      - NM profiles survive reboots and cable reconnects (autoconnect=yes).
      - No gateway / DNS is set → existing internet routes are untouched.
      - Route 192.168.0.0/24 is scoped only to this interface, keeping P2P
        traffic off the default route.
      - Idempotent: the old "p2p-link" profile is deleted first, so re-running
        always produces a clean, correct state.

    NOTE: The interface was set to `managed no` earlier (for the ping-scan
    phase).  We re-enable management here before handing control back to NM.
    """

    # ── 1. Hand the interface back to NetworkManager ──
    print(f"[static-ip] Re-enabling NetworkManager management for {adapter}")
    subprocess.run(
        f"sudo nmcli device set {adapter} managed yes",
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    # ── 2. Remove any existing p2p-link profile (idempotent) ──
    print("[static-ip] Removing old 'p2p-link' profile (if any)")
    subprocess.run(
        "sudo nmcli con delete p2p-link",
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )  # ignoring exit code — it's fine if the profile didn't exist

    # ── 3. Create a fresh persistent connection profile ──
    nmcli_add = (
        f"sudo nmcli con add "
        f"type ethernet "
        f"con-name \"p2p-link\" "
        f"ifname {adapter} "
        f"ipv4.method manual "
        f"ipv4.addresses {ip}/{CIDR} "
        f"ipv4.gateway \"\" "
        f"ipv4.routes \"192.168.0.0/24\" "
        f"ipv4.dns \"\" "
        f"ipv6.method disabled "
        f"connection.autoconnect yes"
    )
    print(f"[static-ip] {nmcli_add}")
    result = subprocess.run(nmcli_add, shell=True)
    if result.returncode != 0:
        print(f"[static-ip] ✗ nmcli con add failed (rc={result.returncode})")
        return

    # ── 4. Activate the profile ──
    print("[static-ip] nmcli con up \"p2p-link\"")
    subprocess.run("sudo nmcli con up \"p2p-link\"", shell=True)


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
        # Tell NetworkManager to leave this interface alone before we touch it.
        # Without this, nmcli auto-config races against our manual ip addr calls
        # and can silently overwrite the temp IP mid-scan.
        print(f"[static-ip] Disabling NetworkManager management for {iface}")
        subprocess.run(
            f"sudo nmcli device set {iface} managed no",
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
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

    # Step 4: clear stale CA keys so fresh CA discovery happens
    #   Old ca_key.pem/ca_cert.pem are tied to the previous IP — keeping them
    #   would make receive.py skip discovery and act as an orphan CA.
    pwd = config.pwd or os.getcwd()
    for stale in ("ca_key.pem", "ca_cert.pem"):
        p = os.path.join(pwd, stale)
        if os.path.exists(p):
            os.remove(p)
            print(f"[static-ip] Removed stale {stale}")

    # Step 5: persist to .env
    env_path = os.path.join(pwd, ".env")
    get_config().write_env("HOST", free_ip, env_path=env_path)
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