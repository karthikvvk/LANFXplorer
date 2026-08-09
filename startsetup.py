import socket, struct
import getpass
import os
import platform
import re, subprocess
import sys
import ipaddress
from pathlib import Path

# CRITICAL: Set up paths FIRST, before importing any local modules
APP_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(APP_DIR))

# Now import local modules
from path_security import get_lanfxplorer_root, ensure_lanfxplorer_directory
from config_manager import get_config_manager
from app_config import get_config

pwd = os.getcwd()
user = getpass.getuser()
# NOTE: Using 'system_type' instead of 'sys' to avoid overwriting the sys module
system_type = platform.system().lower()
password = ""
interface = None
ethernet_interface = None   # best wired Ethernet iface detected (if any)
wifi_interface = None        # best WiFi iface detected (if any)
subnet = None
broadcast_address = None
gateway = None
host_ip = None
cidr = None
port = 4433
# Use secure default paths - $HOME/Lanfxplorer
_secure_root = get_lanfxplorer_root()
out_dir = _secure_root
src_dir = _secure_root
key = os.path.join(pwd, "key.pem")
certi = os.path.join(pwd, "cert.pem")
dest_host = ""
reciv_host = "0.0.0.0"
ca_cert = os.path.join(pwd, "ca_cert.pem")

# ───────────────────────────────────────────────────────────────────────────
# GLOBAL STATE CALL ORDER
# This module uses mutable globals as a configuration database.
# The required call order is:
#
#   1. detect_interface()         — populates: interface, ethernet_interface, wifi_interface
#   2. get_network_info()         — populates: host_ip, cidr, subnet, gateway, broadcast_address
#   3. write_env() / load_env_vars() — reads all of the above
#
# Violating this order (e.g. calling get_network_info before detect_interface) results in
# interface being None and possible fallback to the wrong IP.
#
# Long-term fix: replace these globals with a NetworkContext dataclass so the ordering
# dependency is expressed in function signatures rather than hidden state.
# ───────────────────────────────────────────────────────────────────────────


def detect_interface():
    global host_ip, cidr, interface, ethernet_interface, wifi_interface, system_type, pwd, user, certi, key, out_dir, src_dir, port, broadcast_address, gateway, subnet, dest_host, reciv_host, ca_cert

    if system_type.startswith("linux"):

        # Scan ALL physical interfaces by NAME regardless of IP state.
        # Using `ip link` (not `ip -o -4 addr`) so we detect Ethernet hardware
        # even when the cable is unplugged or p2p-link has not been activated yet.
        link_out = subprocess.check_output(["ip", "-o", "link", "show"], text=True).strip()
        if not link_out:
            raise RuntimeError("No interfaces found (ip link returned empty)")

        SKIP       = ("lo", "veth", "docker", "br-", "cni0", "virbr", "vmnet")
        ETH_PREFS  = ("eth", "enp", "ens", "eno", "en", "lan")
        WIFI_PREFS = ("wlan", "wlp", "wl")
        ethernet_interface = None
        wifi_interface = None

        for line in link_out.splitlines():
            lm = re.match(r'^\d+:\s+([^:@\s]+)', line)
            if not lm:
                continue
            name = lm.group(1)
            low  = name.lower()
            if low == "lo" or any(low.startswith(s) for s in SKIP):
                continue
            if ethernet_interface is None and low.startswith(ETH_PREFS):
                ethernet_interface = name
            if wifi_interface is None and low.startswith(WIFI_PREFS):
                wifi_interface = name

        interface = ethernet_interface or wifi_interface
        if not interface:
            raise Exception("[-] No Ethernet or WiFi interface found")

        print("[+] Detected interface:", interface)
        if ethernet_interface:
            print("[+] Ethernet interface:", ethernet_interface)
        if wifi_interface:
            print("[+] WiFi interface:    ", wifi_interface)

    elif system_type.startswith("win") or system_type.startswith("nt"):
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -ExpandProperty Name"
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        interfaces = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        for i in interfaces:
            u = i.lower()
            if u.startswith(("eth", "en", "wi", "lan")):
                interface = u
                break
        if not interface and interfaces:
            interface = interfaces[0].lower()
        if not interface:
            raise Exception("[-] No Ethernet interface found")

def _get_iface_ip(iface: str):
    """Return (ip_str, cidr_str) for *iface*, or (None, None) if no IPv4 is assigned.

    Populates: host_ip, cidr (indirectly via callers)
    """
    try:
        out = subprocess.check_output(["ip", "-o", "-4", "addr", "show", iface], text=True)
        m = re.search(r'inet\s+([\d\.]+)/(\d+)', out)
        if m:
            return m.group(1), m.group(2)
    except Exception:
        pass
    return None, None


def _fill_network_from_ip(ip: str, cidr_str: str = "24"):
    """Populate global subnet / gateway / broadcast derived from a known *ip*/*cidr_str*.

    Populates: host_ip, cidr, subnet, gateway, broadcast_address

    NOTE: gateway is assumed to be the first host in the network (network+1, e.g. .1 for /24).
    This is a common convention for home routers but is NOT derivable from the subnet alone.
    LANFXplorer is a P2P tool and does not route through the gateway; this value is informational.
    """
    global host_ip, cidr, subnet, gateway, broadcast_address
    host_ip = ip
    cidr = cidr_str
    net = ipaddress.IPv4Network(f"{host_ip}/{cidr}", strict=False)
    subnet            = str(net.netmask)
    broadcast_address = str(net.broadcast_address)
    hosts = list(net.hosts())
    gateway = str(hosts[0]) if hosts else str(net.network_address)


def _check_p2p_connection():
    """
    Query NetworkManager for the 'p2p-link' connection profile state.

    Returns:
        "active"   — profile exists and is currently activated
        "inactive" — profile exists but is not active
        "missing"  — no 'p2p-link' profile found
    """
    try:
        out = subprocess.check_output(
            ["nmcli", "-t", "-f", "NAME,STATE", "con", "show"],
            text=True, stderr=subprocess.DEVNULL
        )
        for line in out.splitlines():
            if line.startswith("p2p-link:"):
                state = line.split(":", 1)[1].strip()
                return "active" if state == "activated" else "inactive"
    except Exception:
        pass
    return "missing"


def _get_profile_ip(profile_name: str = "p2p-link"):
    """
    Read the IP address stored in the NM connection profile (NOT the live
    interface IP).  Returns (ip_str, cidr_str) or (None, None).

    This is different from _get_iface_ip() which reads the running kernel state.
    They can differ after `nmcli con modify` without a subsequent `nmcli con up`.
    """
    try:
        out = subprocess.check_output(
            ["nmcli", "-t", "-f", "ipv4.addresses", "con", "show", profile_name],
            text=True, stderr=subprocess.DEVNULL
        )
        # Output format:  ipv4.addresses:5.10.0.50/24
        for line in out.splitlines():
            if line.startswith("ipv4.addresses:"):
                val = line.split(":", 1)[1].strip()
                if "/" in val:
                    ip, cidr = val.split("/", 1)
                    return ip.strip(), cidr.strip()
                elif val:
                    return val.strip(), "24"
    except Exception:
        pass
    return None, None


def _force_apply_profile_ip(iface: str, new_ip: str, cidr: str, old_ip: str = None):
    """
    Apply *new_ip/cidr* on *iface* immediately using `ip addr` — no NetworkManager
    round-trip, no peer required.  Removes *old_ip* if provided.

    This bridges the gap between `nmcli con modify` (updates stored profile only)
    and `nmcli con up` (re-activates, requires the cable peer to be ready).
    """
    try:
        # Add the new address first so the interface stays live during swap
        subprocess.run(
            ["sudo", "ip", "addr", "replace", f"{new_ip}/{cidr}", "dev", iface],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        # Remove the old address if it differs
        if old_ip and old_ip != new_ip:
            subprocess.run(
                ["sudo", "ip", "addr", "del", f"{old_ip}/{cidr}", "dev", iface],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        print(f"[+] Applied profile IP {new_ip}/{cidr} on {iface} (via ip addr replace)")
    except Exception as e:
        print(f"[!] Could not apply profile IP: {e}")


def get_network_info():
    """Determine host IP and network parameters.

    Populates: host_ip, cidr, subnet, gateway, broadcast_address

    Call order: must be called AFTER detect_interface() so that *interface* is set.

    IP selection priority:
      1. Interface-aware: read the IP directly from the selected *interface* via `ip addr`.
         This is correct for P2P/dual-NIC setups where the P2P Ethernet address matters.
      2. Routing-aware fallback: connect a UDP socket to 8.8.8.8 to let the kernel pick
         the address on the default-route interface.  This is a common trick but can return
         the wrong IP (WiFi instead of Ethernet) on dual-NIC hosts.
    """
    global host_ip, cidr, interface, system_type, pwd, user, certi, key, out_dir, src_dir, port, broadcast_address, gateway, subnet, dest_host, reciv_host, ca_cert

    # ── 1. Interface-aware (preferred) ───────────────────────────────────────────────
    if interface:
        iface_ip, iface_cidr = _get_iface_ip(interface)
        if iface_ip:
            _fill_network_from_ip(iface_ip, iface_cidr or "24")
            return {
                "HOST": host_ip,
                "SUBNET": subnet,
                "CIDR": cidr,
                "GATEWAY": gateway,
                "BROADCAST": broadcast_address,
            }

    # ── 2. Routing-aware fallback (8.8.8.8 trick) ─────────────────────────────────
    # WARNING: On dual-NIC hosts this returns the IP on the default-route interface,
    # which may be WiFi rather than the intended P2P Ethernet interface.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        fallback_ip = s.getsockname()[0]
    except Exception:
        fallback_ip = None
    finally:
        s.close()

    if fallback_ip:
        # Derive CIDR from address class (best-effort; no interface info available)
        ip_parts = list(map(int, fallback_ip.split('.')))
        if ip_parts[0] == 10:
            fallback_cidr = "8"
        elif ip_parts[0] == 172 and 16 <= ip_parts[1] <= 31:
            fallback_cidr = "16"
        else:
            fallback_cidr = "24"
        _fill_network_from_ip(fallback_ip, fallback_cidr)
        return {
            "HOST": host_ip,
            "SUBNET": subnet,
            "CIDR": cidr,
            "GATEWAY": gateway,
            "BROADCAST": broadcast_address,
        }

    raise Exception("[-] Unable to determine host IP")


def load_env_vars():

    global host_ip, cidr, interface, system_type, pwd, user, certi, key, out_dir, src_dir, port, broadcast_address, gateway, subnet, dest_host, reciv_host, ca_cert, password

    # Reload .env → os.environ via AppConfig (no dotenv needed)
    cfg = get_config()
    cfg.reload()

    # Load password from secure keyring storage
    config_mgr = get_config_manager()
    config_mgr.migrate_password_from_env()  # One-time migration
    password = config_mgr.get_password()

    pwd = cfg.pwd or os.getcwd()
    user = cfg.user or getpass.getuser()
    system_type = cfg.system_type or platform.system().lower()
    interface = cfg.interface or interface
    host_ip = cfg.host
    subnet = cfg.subnet
    gateway = cfg.gateway
    broadcast_address = cfg.broadcast
    cidr = cfg.cidr
    port = cfg.port
    out_dir = cfg.out_dir
    src_dir = cfg.src_dir
    certi = cfg.certi
    key = cfg.key
    dest_host = cfg.dest_host
    reciv_host = cfg.reciv_host
    ca_cert = cfg.ca_cert

    print(f"[+] Loaded environment variables from .env")
    return {
        "host": host_ip,
        "port": port,
        "certi": certi,
        "key": key,
        "out_dir": out_dir,
        "src_dir": src_dir,
        "interface": interface,
        "system": system_type,
        "pwd": pwd,
        "user": user,
        "subnet": subnet,
        "gateway": gateway,
        "broadcast": broadcast_address,
        "cidr": cidr,
        "dest_host": dest_host,
        "recivhost": reciv_host,
        "ca_cert": ca_cert,
        "password": password,  # Loaded from secure keyring
    }

def write_env(installer=False):
    global host_ip, cidr, interface, ethernet_interface, wifi_interface, system_type, pwd, user, certi, key, out_dir, src_dir, port, broadcast_address, gateway, subnet, dest_host, reciv_host, ca_cert,password
    detect_interface()
    get_network_info()
    ls = os.listdir(pwd)
    if "key.pem" not in ls or "cert.pem" not in ls:
        # Use cryptography lib on ALL platforms — no standalone openssl binary needed.
        # cryptography bundles its own OpenSSL via cffi, so no system binary is required.
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime

        priv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"quic-server.local")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(priv_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(priv_key, hashes.SHA256())
        )
        with open("key.pem", "wb") as f:
            f.write(priv_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        with open("cert.pem", "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
    # ── Network detection: Ethernet / WiFi priority tree ─────────────────────
    has_eth  = None #ethernet_interface is not None
    has_wifi = wifi_interface is not None

    # Ensure Lanfxplorer directory exists and use it for OUTDIR/SRCDIR
    secure_root = ensure_lanfxplorer_directory()

    
    env_vars = {
        "HOST": host_ip,
        "SUBNET": subnet,
        "CIDR": cidr,
        "GATEWAY": gateway,
        "BROADCAST": broadcast_address,
        "PWD": pwd,
        "USER": user,
        "SYSTEM": system_type,
        "INTERFACE": interface,
        "PORT": port,
        "OUTDIR": secure_root,  # Use secure Lanfxplorer path
        "SRCDIR": secure_root,  # Use secure Lanfxplorer path
        "CERTI": certi,
        "KEY": key,
        "DEST_HOST": dest_host,
        "RECIVHOST": reciv_host,
        "CA_CERT": os.path.join(pwd, "ca_cert.pem"),
        "INSTALLER": "true" if installer else "false",
        "PASSWORD": password,
    }

    # Write all env vars in one call (replaces the set_key loop)
    env_file = str(APP_DIR / ".env")
    get_config().write_env_bulk(
        {k: str(v) for k, v in env_vars.items()},
        env_path=env_file
    )
    # Reload singleton so subsequent get_config() calls see new values
    get_config().reload()

    print(f"\n[+] Environment variables updated in {env_file}")


def setup_pki_and_write_env():
    global host_ip, cidr, interface, system_type, pwd, user, certi, key, out_dir, src_dir, port, broadcast_address, gateway, subnet, dest_host, reciv_host, ca_cert
    import asyncio
    from pki.ca_service import CAManager
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    print("[*] Starting P2P CA Discovery process...")
    

    global pwd, out_dir
    cfg = get_config()
    cfg.reload()
    pwd = cfg.pwd or os.getcwd()
    

    key_file = os.path.join(pwd, "key.pem")
    cert_file = os.path.join(pwd, "cert.pem")
    ca_cert_file = os.path.join(pwd, "ca_cert.pem")
    
    if not os.path.exists(key_file):
        print("    Generating new private key...")
        priv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with open(key_file, "wb") as f:
            f.write(priv_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
    with open(key_file, "rb") as f:
        priv_key_pem = f.read()


    detect_interface()
    get_network_info()
    

    async def run_setup_logic():
        """Run CA discovery and certificate setup logic."""
        # Create CAManager inside async context to ensure asyncio.Event is created in the right loop
        ca_mgr = CAManager(host_ip, pwd)
        
        try:
            # Only start discovery if not already started by a previous call
            if not ca_mgr.discovery_transport:
                await ca_mgr.start_discovery()
            print("    Broadcasting 'WHO_IS_CA'...")
            
            try:
                await asyncio.wait_for(ca_mgr.ca_found_event.wait(), timeout=10.0)
                print(f"    [+] Found CA at {ca_mgr.ca_info}")
                client_cert, ca_cert = await ca_mgr.get_signed_cert(priv_key_pem, f"{user}@{host_ip}")
                with open(cert_file, "wb") as f: 
                    f.write(client_cert)
                with open(ca_cert_file, "wb") as f: 
                    f.write(ca_cert)
                print("    [+] Received signed certificate & CA cert.")
                
            except asyncio.TimeoutError:
                print("    [-] No CA found. Configuring as CA...")
                from pki import utils
                
                ca_cert_pem, ca_key_pem = await ca_mgr.become_ca() 
                
                client_cert = utils.sign_csr(
                    utils.generate_csr(priv_key_pem, f"{user}@{host_ip}", san_ips=[host_ip]),
                    ca_cert_pem,
                    ca_key_pem
                )
                with open(cert_file, "wb") as f: 
                    f.write(client_cert)
                print("    [+] Generated self-signed certificate.")
                
        finally:
            # Always stop discovery to clean up resources
            if ca_mgr.discovery_transport:
                ca_mgr.stop_discovery()
    
    try:
        asyncio.run(run_setup_logic())
        print("[+] PKI setup completed successfully")
    except Exception as e:
        print(f"[!] PKI setup encountered an error: {e}")
        print("[!] Continuing with existing certificates...")
    
    # Always write env vars, even if PKI setup fails
    write_env()

if __name__ == "__main__":
    write_env()

