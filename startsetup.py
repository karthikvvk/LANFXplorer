import socket, struct
import getpass
import os
import platform
import re, subprocess
import sys
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
    """Return (ip_str, cidr_str) for *iface*, or (None, None) if no IPv4 is assigned."""
    try:
        out = subprocess.check_output(["ip", "-o", "-4", "addr", "show", iface], text=True)
        m = re.search(r'inet\s+([\d\.]+)/(\d+)', out)
        if m:
            return m.group(1), m.group(2)
    except Exception:
        pass
    return None, None


def _fill_network_from_ip(ip: str, cidr_str: str = "24"):
    """Populate global subnet / gateway / broadcast derived from a known *ip*/*cidr_str*."""
    global host_ip, cidr, subnet, gateway, broadcast_address
    host_ip = ip
    cidr = cidr_str
    mask_int = (0xFFFFFFFF << (32 - int(cidr))) & 0xFFFFFFFF
    subnet = socket.inet_ntoa(struct.pack("!I", mask_int))
    ip_int    = struct.unpack("!I", socket.inet_aton(host_ip))[0]
    subnet_int = struct.unpack("!I", socket.inet_aton(subnet))[0]
    network_int   = ip_int & subnet_int
    broadcast_int = network_int | (~subnet_int & 0xFFFFFFFF)
    gateway_int   = network_int + 1
    gateway           = socket.inet_ntoa(struct.pack("!I", gateway_int))
    broadcast_address = socket.inet_ntoa(struct.pack("!I", broadcast_int))


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




    global host_ip, cidr, interface, system_type, pwd, user, certi, key, out_dir, src_dir, port, broadcast_address, gateway, subnet, dest_host, reciv_host, ca_cert


    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        host_ip = s.getsockname()[0]
    except Exception:

        try:
            if interface:
                out = subprocess.check_output(["ip", "-o", "addr", "show", interface], text=True)

                m = re.search(r'inet\s+([\d\.]+)/(\d+)\s+brd\s+([\d\.]+)', out)
                if m:
                    host_ip = m.group(1)
                    cidr = m.group(2)
                    broadcast_address = m.group(3)
        except Exception:
            pass
    finally:
        s.close()

    if not host_ip:
        raise Exception("[-] Unable to determine host IP")


    if not cidr:
        ip_parts = list(map(int, host_ip.split('.')))
        if ip_parts[0] == 10:
            cidr = "8"
            subnet = "255.0.0.0"
        elif ip_parts[0] == 172 and 16 <= ip_parts[1] <= 31:
            cidr = "16"
            subnet = "255.255.0.0"
        elif ip_parts[0] == 192 and ip_parts[1] == 168:
            cidr = "24"
            subnet = "255.255.255.0"
        else:
            cidr = "24"
            subnet = "255.255.255.0"
    else:

        mask_int = (0xFFFFFFFF << (32 - int(cidr))) & 0xFFFFFFFF
        subnet = socket.inet_ntoa(struct.pack("!I", mask_int))


    ip_int = struct.unpack("!I", socket.inet_aton(host_ip))[0]
    subnet_int = struct.unpack("!I", socket.inet_aton(subnet))[0]
    network_int = ip_int & subnet_int
    broadcast_int = network_int | (~subnet_int & 0xFFFFFFFF)
    gateway_int = network_int + 1

    gateway = socket.inet_ntoa(struct.pack("!I", gateway_int))
    broadcast = socket.inet_ntoa(struct.pack("!I", broadcast_int))


    gateway = gateway
    broadcast_address = broadcast


    return {
        "HOST": host_ip,
        "SUBNET": subnet,
        "CIDR": cidr,
        "GATEWAY": gateway,
        "BROADCAST": broadcast
    }

def load_env_vars():

    global host_ip, cidr, interface, system_type, pwd, user, certi, key, out_dir, src_dir, port, broadcast_address, gateway, subnet, dest_host, reciv_host, ca_cert

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
    global host_ip, cidr, interface, ethernet_interface, wifi_interface, system_type, pwd, user, certi, key, out_dir, src_dir, port, broadcast_address, gateway, subnet, dest_host, reciv_host, ca_cert
    detect_interface()
    ls = os.listdir(pwd)
    if "key.pem" not in ls or "cert.pem" not in ls:
        # Use full path to openssl on Windows to avoid DLL conflicts with cryptography package
        if platform.system().lower().startswith("win"):
            openssl_exe = os.environ.get("OPENSSL_PATH", r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe")
            subprocess.run([
                openssl_exe, "req", "-x509", "-nodes",
                "-newkey", "rsa:2048",
                "-keyout", "key.pem", "-out", "cert.pem",
                "-days", "365", "-subj", "/CN=quic-server.local"
            ])
        else:
            # Generate self-signed cert using Python cryptography (avoids system openssl
            # version mismatch caused by LD_LIBRARY_PATH pointing to bundled openssl libs)
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
    has_eth  = ethernet_interface is not None
    has_wifi = wifi_interface is not None

    if has_eth:
        interface = ethernet_interface
        p2p_status = _check_p2p_connection()
        eth_ip,  eth_cidr = None, "24"

        if p2p_status == "active":
            # Profile is running — grab the IP it assigned
            eth_ip, eth_cidr = _get_iface_ip(ethernet_interface)
            if eth_ip:
                print(f"[+] p2p-link active — using {eth_ip}")
            else:
                # Activated but IP not visible yet — treat as inactive
                print("[!] p2p-link active but IP not visible — re-activating...")
                p2p_status = "inactive"

        if p2p_status == "inactive":        # separate `if` allows fall-through from above
            print("[!] p2p-link exists but is down — bringing it up...")
            subprocess.run(
                ["nmcli", "con", "up", "p2p-link"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            # Poll until the IP appears (up to 10 s)
            import time as _t
            deadline = _t.time() + 10
            while _t.time() < deadline:
                eth_ip, eth_cidr = _get_iface_ip(ethernet_interface)
                if eth_ip:
                    break
                _t.sleep(0.5)
            if eth_ip:
                print(f"[+] p2p-link brought up — using {eth_ip}")
            else:
                raise RuntimeError(
                    f"p2p-link activated but no IP appeared on {ethernet_interface}")

        elif p2p_status == "missing":
            # No profile at all — run ping-scan + create nmcli p2p-link
            if has_wifi:
                print("[!] No p2p-link (WiFi active) — scanning + creating P2P profile...")
            else:
                print("[!] No p2p-link — scanning + creating P2P profile...")
            from set_static_ip import assign_static_ip
            chosen = assign_static_ip(interface_override=ethernet_interface)
            if not chosen:
                raise RuntimeError("Could not assign a static IP on Ethernet")
            eth_ip, eth_cidr = chosen, "24"

        _fill_network_from_ip(eth_ip, eth_cidr or "24")
        if has_wifi:
            print(f"[+] Ethernet + WiFi — P2P on {eth_ip} (WiFi stays active)")

    elif has_wifi:
        # ── WiFi only — use existing network config, no static IP needed ──────
        print("[+] WiFi-only mode — using existing network configuration")
        get_network_info()

    else:
        raise RuntimeError("[-] No network interface found (no Ethernet, no WiFi) — cannot start")


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
