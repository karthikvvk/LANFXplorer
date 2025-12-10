#!/usr/bin/env python3

import argparse
import os
from pathlib import Path
from elevate import elevate
from ownca import CertificateAuthority
elevate()

def issue_peer_certificate() -> None:
    parser = argparse.ArgumentParser(
        description="Issue a LANFXplorer peer certificate using OwnCA."
    )

    parser.add_argument(
        "--peer-name",
        required=True,
        help="Logical peer name, used as CN and DNS name (e.g. peerA.lanfx.local).",
    )

    parser.add_argument(
        "--ca-storage",
        default="/opt/lanfx_ca",
        help="Directory where OwnCA stores the CA (default: /opt/lanfx_ca).",
    )

    parser.add_argument(
        "--export-base",
        default="/opt/lanfx_ca_export/peers",
        help="Base directory where peer certs/keys are exported.",
    )

    parser.add_argument(
        "--days",
        type=int,
        default=825,
        help="Validity in days for the peer certificate (default: 825).",
    )

    args = parser.parse_args()

    ca_storage_dir = Path(args.ca_storage)
    export_base_dir = Path(args.export_base)
    peer_name = args.peer_name

    if not ca_storage_dir.exists():
        raise SystemExit(
            f"CA storage directory {ca_storage_dir} does not exist. "
            f"Run ca_init.py first."
        )

    if not export_base_dir.exists():
        export_base_dir.mkdir(parents=True, exist_ok=True)

    ca = CertificateAuthority(
        ca_storage=str(ca_storage_dir),
        common_name="LANFXplorer Root CA",
    )

    dns_names = [peer_name]

    host_cert = ca.issue_certificate(
        hostname=peer_name,
        dns_names=dns_names,
        maximum_days=args.days,
        ca=False,
    )

    peer_export_dir = export_base_dir / peer_name
    if not peer_export_dir.exists():
        peer_export_dir.mkdir(parents=True, exist_ok=True)

    cert_path = peer_export_dir / "cert.pem"
    key_path = peer_export_dir / "key.pem"

    cert_bytes = host_cert.cert_bytes
    key_bytes = host_cert.key_bytes

    with cert_path.open("wb") as cert_file:
        cert_file.write(cert_bytes)

    with key_path.open("wb") as key_file:
        key_file.write(key_bytes)

    print("Issued certificate for peer:", peer_name)
    print("  Exported certificate:", cert_path)
    print("  Exported private key:", key_path)


if __name__ == "__main__":
    issue_peer_certificate()
