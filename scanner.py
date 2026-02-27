import getpass
import os
import subprocess
import platform
import re
import asyncio
from ipaddress import IPv4Network, IPv4Address
import concurrent.futures
from typing import List, Set, Optional, Dict
from dotenv import load_dotenv
import requests
import socket
import time
import sys

# Import centralized configuration
from app_config import AppConfig


# ==================== GLOBAL STATE ====================
host_ip = ""
cidr = ""
gateway = ""
subnet = ""
broadcast = ""
interface = ""
system_name = ""
user = ""
pwd = ""
dest_host = ""
file_path = ""


# ==================== UTILITY FUNCTIONS ====================

def check_subnet(ip: str, host_ip: str) -> bool:
    """Check if an IP is on the same subnet as host_ip, excluding gateway/broadcast/special."""
    if not host_ip:
        raise ValueError("HOST environment variable not set")

    ip_parts = ip.strip().split('.')
    default_parts = host_ip.strip().split('.')
    ed = ip_parts[-1]

    if ed == '1' or ed == "200" or ed == "255":
        return False

    return ip_parts[:-1] == default_parts[:-1]


def get_OS_TYPE(REMOTE_HOST: str = "") -> Dict:
    """Query a remote host for its OS type and username via the app's API."""
    try:
        response = requests.post(f"http://{REMOTE_HOST}:5000/osinfo",
                                json={"request": "osinfo"}, timeout=3)
        if response.status_code == 200:
            data = response.json()
            return {"os": data.get("os", "linux"), "user": data.get("user")}
        else:
            return {"os": "linux", "user": None}
    except Exception:
        return {"os": "linux", "user": None}


def update_env():
    """Load environment variables from .env file."""
    global gateway, cidr, file_path, host_ip, broadcast, system_name, interface, user, pwd, dest_host

    load_dotenv()

    host_ip = os.getenv("HOST", "")
    cidr = os.getenv("CIDR", "24")
    gateway = os.getenv("GATEWAY", "")
    subnet = os.getenv("SUBNET", "255.255.255.0")
    broadcast = os.getenv("BROADCAST", "")
    interface = os.getenv("INTERFACE", "")
    system_name = os.getenv("SYSTEM", platform.system().lower())
    user = os.getenv("USER", getpass.getuser())
    pwd = os.getenv("PWD", os.getcwd())
    dest_host = os.getenv("DEST_HOST", "")

    print(f"[+] Loaded scanner's environment variables")
    print(f"    Network: {gateway}/{cidr}")
    print(f"    Interface: {interface}")
    print(f"    System: {system_name}")


# ==================== STEP 1 & 3: ARP CACHE READING ====================

def read_arp_cache() -> Set[str]:
    """
    Read the ARP cache to get known neighbor IPs.
    Uses 'ip neigh' on Linux, 'arp -a' on Windows/macOS.
    """
    system = platform.system().lower()
    ips = set()

    try:
        if system == "linux":
            result = subprocess.run(
                ["ip", "neigh"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                # Parse lines like: "192.168.1.5 dev wlan0 lladdr aa:bb:cc:dd:ee:ff REACHABLE"
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    # Skip entries marked FAILED (no valid ARP response)
                    if "FAILED" in line.upper():
                        continue
                    match = re.match(r'(\d{1,3}(?:\.\d{1,3}){3})', line)
                    if match:
                        ips.add(match.group(1))
        else:
            # Windows / macOS: arp -a
            result = subprocess.run(
                ["arp", "-a"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                found = re.findall(r'(\d{1,3}(?:\.\d{1,3}){3})', result.stdout)
                ips.update(found)
    except Exception as e:
        print(f"[!] ARP cache read failed: {e}", file=sys.stderr)

    return ips


# ==================== STEP 2: PING SWEEP ====================

def _ping_one(ip: str) -> Optional[str]:
    """
    Ping a single IP with a short timeout.
    Returns the IP if reachable, None otherwise.
    This populates the system's ARP cache as a side effect.
    """
    system = platform.system().lower()
    try:
        if system == "linux":
            res = subprocess.run(
                ["ping", "-c", "1", "-W", "1", ip],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=2
            )
        else:
            # Windows
            res = subprocess.run(
                ["ping", "-n", "1", "-w", "200", ip],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=2
            )
        return ip if res.returncode == 0 else None
    except Exception:
        return None


def ping_sweep_subnet(host_ip: str, cidr: str = "24") -> Set[str]:
    """
    Ping sweep the entire subnet to discover reachable hosts
    and populate the ARP cache for subsequent reads.
    Uses threaded parallel pings with short timeouts.
    """
    if not host_ip:
        print("[!] Cannot ping sweep: no host IP set", file=sys.stderr)
        return set()

    try:
        gateway_ip = host_ip
        network = IPv4Network(f"{gateway_ip}/{cidr}", strict=False)
    except Exception as e:
        print(f"[!] Invalid network for ping sweep: {e}", file=sys.stderr)
        return set()

    ip_list = [str(ip) for ip in network.hosts()]

    # Cap at reasonable size to avoid excessive pinging
    if len(ip_list) > 1024:
        ip_list = ip_list[:1024]

    print(f"[*] Ping sweeping {len(ip_list)} addresses in {network}...")

    alive = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        futures = {executor.submit(_ping_one, ip): ip for ip in ip_list}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                alive.add(result)

    print(f"[+] Ping sweep found {len(alive)} reachable hosts")
    return alive


# ==================== STEP 4: PER-HOST APP PROBE ====================

def probe_peer(ip: str, timeout: float = 2.0) -> Optional[str]:
    """
    Send a WHO_IS_PEER UDP message to a single IP and wait for I_AM_PEER response.
    Returns the peer's reported IP if it responds, None otherwise.
    """
    config = AppConfig()
    DISCOVERY_PORT = config.PEER_DISCOVERY_PORT
    PEER_DISCOVERY_MSG = config.PEER_DISCOVERY_MSG
    PEER_RESPONSE_PREFIX = config.PEER_RESPONSE_PREFIX

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)

        sock.sendto(PEER_DISCOVERY_MSG, (ip, DISCOVERY_PORT))

        try:
            data, addr = sock.recvfrom(4096)
            if data.startswith(PEER_RESPONSE_PREFIX):
                parts = data.decode().split()
                if len(parts) >= 2:
                    return parts[1]
                return addr[0]
        except socket.timeout:
            return None

        sock.close()
    except Exception:
        return None

    return None


def probe_peers_batch(ips: Set[str], timeout: float = 1.5) -> Set[str]:
    """
    Probe multiple IPs in parallel via threadpool to find which ones
    are running the LANFXplorer app (respond to WHO_IS_PEER).
    """
    verified = set()

    if not ips:
        return verified

    print(f"[*] Probing {len(ips)} hosts for app broadcast response...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(probe_peer, ip, timeout): ip for ip in ips}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                verified.add(result)

    print(f"[+] {len(verified)} hosts responded to app probe")
    return verified


# ==================== MAIN DISCOVERY: gethostlist ====================

def gethostlist() -> List[Dict]:
    """
    Multi-step peer discovery — always does full sweep for worst-case coverage.

    Flow:
      1. Read ARP cache (ip neigh) — instant, what we already know
      2. Test ARP hosts for app availability (WHO_IS_PEER) — output found peers immediately
      3. ALWAYS do full ping sweep bruteforce — discovers hosts missed by ARP
         For each newly found host, probe for app and output immediately
      4. For all verified peers, fetch OS info

    Returns list of dicts: [{"host": ip, "user": username, "os": os_type}, ...]
    """
    global host_ip, cidr

    update_env()

    if not host_ip:
        print("[!] HOST not set — cannot scan", file=sys.stderr)
        return []

    verified_peers = set()

    # ── Step 1: Read ARP cache (what we already know) ──
    print("[*] Step 1: Reading ARP cache (ip neigh)...")
    arp_hosts = read_arp_cache()

    # Filter to same subnet, exclude self
    arp_candidates = set()
    for ip in arp_hosts:
        if ip == host_ip:
            continue
        try:
            if check_subnet(ip, host_ip):
                arp_candidates.add(ip)
        except ValueError:
            continue

    print(f"    {len(arp_candidates)} hosts in ARP cache (same subnet)")

    # ── Step 2: Test ARP hosts for app availability ──
    if arp_candidates:
        print("[*] Step 2: Testing ARP hosts for LANFXplorer app...")
        arp_verified = probe_peers_batch(arp_candidates, timeout=1.5)
        for peer in arp_verified:
            print(f"    [FOUND] {peer} — app detected (from ARP cache)")
            verified_peers.add(peer)
    else:
        print("[*] Step 2: No ARP hosts to test, skipping...")

    # ── Step 3: ALWAYS do full ping sweep bruteforce ──
    # Even if we already found hosts, sweep the entire subnet
    # to discover hosts not yet in ARP cache (worst-case scenario)
    print("[*] Step 3: Full ping sweep (bruteforce) of subnet...")
    sweep_found = ping_sweep_subnet(host_ip, cidr)

    # Find NEW hosts (not already tested from ARP cache)
    new_candidates = set()
    for ip in sweep_found:
        if ip == host_ip:
            continue
        try:
            if check_subnet(ip, host_ip) and ip not in arp_candidates:
                new_candidates.add(ip)
        except ValueError:
            continue

    if new_candidates:
        print(f"    {len(new_candidates)} NEW hosts found beyond ARP cache")
        print("[*] Step 3b: Testing new hosts for LANFXplorer app...")
        new_verified = probe_peers_batch(new_candidates, timeout=1.5)
        for peer in new_verified:
            print(f"    [FOUND] {peer} — app detected (from ping sweep)")
            verified_peers.add(peer)
    else:
        print("    No new hosts found beyond ARP cache")

    # Also try a general UDP broadcast (catches peers missed by unicast)
    print("[*] Bonus: UDP broadcast scan...")
    broadcast_peers = scan_peers_udp()
    for bp in broadcast_peers:
        if bp != host_ip and bp not in verified_peers:
            print(f"    [FOUND] {bp} — app detected (from broadcast)")
            verified_peers.add(bp)

    if not verified_peers:
        print("[!] No LANFXplorer peers found on the network")
        return []

    # ── Step 4: Get OS info for verified peers ──
    print(f"[*] Step 4: Fetching OS info for {len(verified_peers)} verified peers...")
    result = []
    for ip in verified_peers:
        res = get_OS_TYPE(ip)
        username = res.get("user")
        if username:
            result.append({
                "host": ip,
                "user": username,
                "os": res.get("os", "linux")
            })
        else:
            # Peer responded to WHO_IS_PEER but /osinfo failed
            result.append({
                "host": ip,
                "user": "unknown",
                "os": res.get("os", "linux")
            })

    print(f"[+] Discovery complete: {len(result)} peer(s) found")
    return result


# ==================== UDP BROADCAST SCAN (kept as utility) ====================

def scan_peers_udp(network=None) -> List[str]:
    """Scan for peers using UDP broadcast. Used as a supplementary method."""
    config = AppConfig()
    DISCOVERY_PORT = config.PEER_DISCOVERY_PORT
    PEER_DISCOVERY_MSG = config.PEER_DISCOVERY_MSG
    PEER_RESPONSE_PREFIX = config.PEER_RESPONSE_PREFIX
    target_broadcast = config.broadcast or '<broadcast>'

    found = set()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(2.0)

        try:
            sock.sendto(PEER_DISCOVERY_MSG, (target_broadcast, DISCOVERY_PORT))
        except Exception:
            pass

        start_time = time.time()
        while time.time() - start_time < 2.0:
            try:
                data, addr = sock.recvfrom(4096)
                if data.startswith(PEER_RESPONSE_PREFIX):
                    parts = data.decode().split()
                    if len(parts) >= 2:
                        found.add(parts[1])
                    else:
                        found.add(addr[0])
            except socket.timeout:
                break
            except Exception:
                pass

        sock.close()
    except Exception as e:
        print(f"[!] Peer UDP Scan failed: {e}", file=sys.stderr)

    return list(found)


# ==================== PEER DISCOVERY LISTENER (CANONICAL) ====================

class PeerDiscoveryListener:
    """Asyncio-based peer discovery listener - CANONICAL implementation."""

    # Use centralized constants from AppConfig
    DISCOVERY_PORT = AppConfig.PEER_DISCOVERY_PORT
    PEER_DISCOVERY_MSG = AppConfig.PEER_DISCOVERY_MSG
    PEER_RESPONSE_PREFIX = AppConfig.PEER_RESPONSE_PREFIX

    def __init__(self, host_ip: str):

        self.host_ip = host_ip
        self.transport = None
        self.protocol = None

    class Protocol(asyncio.DatagramProtocol):

        def __init__(self, host_ip: str):
            self.host_ip = host_ip
            self.transport = None

        def connection_made(self, transport):
            self.transport = transport

        def datagram_received(self, data: bytes, addr: tuple):
            if data == PeerDiscoveryListener.PEER_DISCOVERY_MSG:
                response = f"{PeerDiscoveryListener.PEER_RESPONSE_PREFIX.decode()} {self.host_ip}".encode()
                self.transport.sendto(response, addr)

    async def start(self):
        loop = asyncio.get_running_loop()

        # Use reuse_port=True to allow restart without 'address already in use' error
        self.transport, self.protocol = await loop.create_datagram_endpoint(
            lambda: self.Protocol(self.host_ip),
            local_addr=('0.0.0.0', self.DISCOVERY_PORT),
            allow_broadcast=True,
            reuse_port=True  # Allow port reuse on restart
        )
        print(f"[+] Peer Discovery Listener started on port {self.DISCOVERY_PORT}")

    def stop(self):
        if self.transport:
            self.transport.close()
            print(f"[+] Peer Discovery Listener stopped")


async def start_peer_discovery_listener(host_ip: str) -> PeerDiscoveryListener:

    listener = PeerDiscoveryListener(host_ip)
    await listener.start()
    return listener
