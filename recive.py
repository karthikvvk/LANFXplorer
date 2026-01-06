#!/usr/bin/env python3
import asyncio
import os
import sys
import getpass
from pathlib import Path

# CRITICAL: Set up paths FIRST, before importing any local modules
APP_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(APP_DIR))

# Now import local modules
from startsetup import load_env_vars
from receiver_api_functions import start_receiver, stop_receiver
from path_security import get_lanfxplorer_root, validate_path_access, ensure_lanfxplorer_directory
from config_manager import get_password

def on_file_received(filepath: str, filesize: int) -> None:

    print(f"[receiver] Received file: {filepath} ({filesize} bytes)")


async def main() -> None:
    env = load_env_vars()

    recivhost = env.get("recivhost") or "0.0.0.0"
    port = env.get("port") or 4433
    cert_path = env.get("certi") or "cert.pem"
    key_path = env.get("key") or "key.pem"
    ca_cert = env.get("ca_cert") or env.get("CA_CERT")
    user = env.get("user") or getpass.getuser()
    
    # SECURITY: Use Lanfxplorer directory as default, validate configured out_dir
    configured_out_dir = env.get("out_dir")
    if configured_out_dir:
        is_valid, error_msg = validate_path_access(configured_out_dir)
        if not is_valid:
            print(f"[receiver] SECURITY WARNING: {error_msg}")
            print(f"[receiver] Using default Lanfxplorer directory instead.")
            out_dir = ensure_lanfxplorer_directory()
        else:
            out_dir = configured_out_dir
    else:
        out_dir = ensure_lanfxplorer_directory()

    # NOTE: Certificate (cert.pem) may not exist on first run - it will be generated
    # during CA discovery below. Key will also be generated if missing.
    # We only check these paths exist AFTER CA discovery completes.

    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    print(f"[receiver] Loaded from env:")
    print(f"          RECIVHOST={recivhost}")
    print(f"          PORT={port}")
    print(f"          CERTI={cert_path}")
    print(f"          KEY={key_path}")
    print(f"          OUTDIR={out_dir}")

    from pki.ca_service import CAManager
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    
    ca_ip = env.get("host") or recivhost
    ca_mgr = CAManager(ca_ip, os.getcwd())
    
    if ca_mgr.check_ca_status():
        print(f"[receiver] CA keys found in {os.getcwd()}. Starting CA Service (Signing + Discovery)...")
        print(f"[receiver] CA will be advertised at {ca_ip}")
        await ca_mgr.start_ca_service()
    else:
        print("[receiver] No CA keys found locally. Running as standard peer.")
        print("[receiver] Attempting CA discovery on network...")
        
        if not os.path.isfile(key_path):
            print("[receiver] Generating private key...")
            priv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            with open(key_path, "wb") as f:
                f.write(priv_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                ))
        
        with open(key_path, "rb") as f:
            priv_key_pem = f.read()
        
        await ca_mgr.start_discovery()
        print("[receiver] Broadcasting 'WHO_IS_CA'...")
        
        try:
            await asyncio.wait_for(ca_mgr.ca_found_event.wait(), timeout=5.0)
            print(f"[receiver] ✓ Found CA at {ca_mgr.ca_info}")
            
            print("[receiver] Requesting certificate signature from CA...")
            client_cert, ca_cert_pem = await ca_mgr.get_signed_cert(priv_key_pem, f"{user}@{ca_ip}")
            
            with open(cert_path, "wb") as f:
                f.write(client_cert)
            with open(ca_cert or "ca_cert.pem", "wb") as f:
                f.write(ca_cert_pem)
            
            if not ca_cert:
                ca_cert = os.path.join(os.getcwd(), "ca_cert.pem")
            
            print("[receiver] ✓ Received signed certificate & CA cert from network CA")
            ca_mgr.stop_discovery()
            
        except asyncio.TimeoutError:
            print("[receiver] ✗ No CA found on network. Becoming Root CA...")
            ca_cert_pem, ca_key_pem = await ca_mgr.become_ca()
            
            from pki.utils import sign_csr, generate_csr
            csr = generate_csr(priv_key_pem, f"{user}@{ca_ip}", san_ips=[ca_ip])
            client_cert = sign_csr(csr, ca_cert_pem, ca_key_pem)
            
            with open(cert_path, "wb") as f:
                f.write(client_cert)
            
            if not ca_cert:
                ca_cert = os.path.join(os.getcwd(), "ca_cert.pem")
            
            print("[receiver] ✓ Configured as network CA")
            print(f"[receiver] CA will be advertised at {ca_ip}")

    # === Post-CA-Discovery Validation ===
    # Now verify that certificates were properly generated
    if not os.path.isfile(cert_path):
        print(f"[receiver] ERROR: Certificate generation failed - {cert_path} not found")
        print(f"[receiver] CA discovery did not produce a valid certificate.")
        sys.exit(1)
    
    if not os.path.isfile(key_path):
        print(f"[receiver] ERROR: Key file not found: {key_path}")
        sys.exit(1)
    
    print(f"[receiver] ✓ Certificates validated: {cert_path}, {key_path}")

    from scanner import start_peer_discovery_listener
    peer_listener = await start_peer_discovery_listener(ca_ip)
    print(f"[receiver] Peer discovery active on UDP port 4436")

    from pki.handshake import start_handshake_service
    
    if not ca_cert:
        ca_cert = os.path.join(os.getcwd(), "ca_cert.pem")
        print(f"[receiver] CA_CERT not in env, using default: {ca_cert}")
    
    if not os.path.isfile(ca_cert):
        print(f"[receiver] ERROR: CA certificate not found: {ca_cert}")
        print(f"[receiver] Please run 'python startsetup.py' first to initialize certificates")
        sys.exit(1)
    
    # Password is loaded from secure keyring storage via config_manager
    password = get_password()
    if not password:
        print(f"[receiver] WARNING: PASSWORD not set. Use config manager to set password.")
    else:
        print(f"[receiver] Password authentication enabled")
    
    handshake_service = await start_handshake_service(
        host=ca_ip,
        cert_path=cert_path,
        ca_cert_path=ca_cert
    )

    server = await start_receiver(
        host=recivhost,
        port=port,
        certificate=cert_path,
        private_key=key_path,
        ca_cert=ca_cert,
        require_client_cert=False,  # aioquic can't reliably extract certs - use password auth
        on_file_received=on_file_received,
        save_dir=out_dir,
    )

    print(f"[receiver] QUIC Receiver listening on {recivhost}:{port}")
    print(f"[receiver] All services running:")
    print(f"           - Peer Discovery (UDP:4436)")
    print(f"           - Handshake Service (TCP:4437)")
    print(f"           - QUIC File Transfer (UDP:{port})")
    if ca_mgr.check_ca_status():
        print(f"           - CA Service (UDP:4434, TCP:4435)")
    print("[receiver] Press Ctrl+C to stop.")

    try:
        await asyncio.Future()  
    finally:
        await stop_receiver(server)
        print("[receiver] Server stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[receiver] KeyboardInterrupt, exiting.")
