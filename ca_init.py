#!/usr/bin/env python3

import os
from pathlib import Path
from elevate import elevate
from ownca import CertificateAuthority

elevate()

def initialize_ca() -> None:
    ca_storage_dir = Path("/opt/lanfx_ca")
    export_dir = Path("/opt/lanfx_ca_export/ca")

    if not ca_storage_dir.exists():
        ca_storage_dir.mkdir(parents=True, exist_ok=True)

    if not export_dir.exists():
        export_dir.mkdir(parents=True, exist_ok=True)

    common_name = "LANFXplorer Root CA"

    ca = CertificateAuthority(
        ca_storage=str(ca_storage_dir),
        common_name=common_name
    )

    ca_cert_bytes = ca.cert_bytes

    ca_export_path = export_dir / "lanfx_root_ca.crt"
    with ca_export_path.open("wb") as ca_file:
        ca_file.write(ca_cert_bytes)

    print("CA initialized or loaded.")
    print("CA storage directory:", ca_storage_dir)
    print("Exported CA certificate:", ca_export_path)


if __name__ == "__main__":
    initialize_ca()
