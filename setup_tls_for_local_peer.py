#!/usr/bin/env python3

import getpass
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID


def get_project_root() -> Path:
    script_path = Path(__file__).resolve()
    project_root = script_path.parent
    return project_root


# ---------------- CA helpers ----------------

def generate_ca_key() -> rsa.RSAPrivateKey:
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )
    return key

def build_ca_certificate(
    ca_key: rsa.RSAPrivateKey,
    common_name: str,
    days_valid: int = 3650,
) -> x509.Certificate:
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )
    issuer = subject  # self-signed

    now = datetime.now(timezone.utc)
    cert_builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=days_valid))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
    )

    ca_cert = cert_builder.sign(
        private_key=ca_key,
        algorithm=hashes.SHA256(),
    )
    return ca_cert


def save_private_key_pem(
    key: rsa.RSAPrivateKey,
    path: Path,
    password: bytes | None = None,
) -> None:
    if password is None:
        encryption = serialization.NoEncryption()
    else:
        encryption = serialization.BestAvailableEncryption(password)

    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    )

    with path.open("wb") as f:
        f.write(pem)


def load_private_key_pem(path: Path, password: bytes | None = None) -> rsa.RSAPrivateKey:
    with path.open("rb") as f:
        data = f.read()
    key = serialization.load_pem_private_key(data, password=password)
    return key


def save_cert_pem(cert: x509.Certificate, path: Path) -> None:
    pem = cert.public_bytes(encoding=serialization.Encoding.PEM)
    with path.open("wb") as f:
        f.write(pem)


def load_cert_pem(path: Path) -> x509.Certificate:
    with path.open("rb") as f:
        data = f.read()
    cert = x509.load_pem_x509_certificate(data)
    return cert


# ---------------- Peer helpers ----------------

def generate_peer_key() -> rsa.RSAPrivateKey:
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    return key


def build_peer_certificate(
    peer_key: rsa.RSAPrivateKey,
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    peer_name: str,
    days_valid: int = 825,
) -> x509.Certificate:
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, peer_name),
        ]
    )

    issuer = ca_cert.subject

    now = datetime.now(timezone.utc)
    san = x509.SubjectAlternativeName(
        [
            x509.DNSName(peer_name),
        ]
    )

    cert_builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(peer_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=days_valid))
        .add_extension(
            san,
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage(
                [
                    ExtendedKeyUsageOID.SERVER_AUTH,
                    ExtendedKeyUsageOID.CLIENT_AUTH,
                ]
            ),
            critical=False,
        )
    )

    peer_cert = cert_builder.sign(
        private_key=ca_key,
        algorithm=hashes.SHA256(),
    )
    return peer_cert


# ---------------- Main workflow ----------------

def init_or_load_ca(
    ca_storage_dir: Path,
    export_ca_dir: Path,
) -> tuple[Path, rsa.RSAPrivateKey, x509.Certificate]:
    if not ca_storage_dir.exists():
        ca_storage_dir.mkdir(parents=True, exist_ok=True)

    if not export_ca_dir.exists():
        export_ca_dir.mkdir(parents=True, exist_ok=True)

    ca_key_path = ca_storage_dir / "ca_key.pem"
    ca_cert_path = ca_storage_dir / "ca_cert.pem"
    ca_export_path = export_ca_dir / "lanfx_root_ca.crt"

    if ca_key_path.exists() and ca_cert_path.exists():
        ca_key = load_private_key_pem(ca_key_path, password=None)
        ca_cert = load_cert_pem(ca_cert_path)
        print("[CA] Loaded existing CA:")
        print("     key :", ca_key_path)
        print("     cert:", ca_cert_path)
    else:
        print("[CA] Creating new CA ...")
        ca_key = generate_ca_key()
        ca_cert = build_ca_certificate(
            ca_key=ca_key,
            common_name="LANFXplorer Root CA",
            days_valid=3650,
        )
        save_private_key_pem(ca_key, ca_key_path, password=None)
        save_cert_pem(ca_cert, ca_cert_path)
        print("[CA] Created new CA:")
        print("     key :", ca_key_path)
        print("     cert:", ca_cert_path)

    # Export CA cert for clients
    save_cert_pem(ca_cert, ca_export_path)
    print("     exported CA cert:", ca_export_path)

    return ca_export_path, ca_key, ca_cert


def init_or_load_peer(
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    peers_export_base: Path,
    peer_name: str,
    days_valid: int = 825,
) -> tuple[Path, Path]:
    if not peers_export_base.exists():
        peers_export_base.mkdir(parents=True, exist_ok=True)

    peer_export_dir = peers_export_base / peer_name
    peer_cert_path = peer_export_dir / "cert.pem"
    peer_key_path = peer_export_dir / "key.pem"

    if peer_cert_path.exists() and peer_key_path.exists():
        print("[PEER] Loaded existing cert/key for:", peer_name)
        print("       cert:", peer_cert_path)
        print("       key :", peer_key_path)
        return peer_cert_path, peer_key_path

    print("[PEER] Creating new cert/key for:", peer_name)

    peer_key = generate_peer_key()
    peer_cert = build_peer_certificate(
        peer_key=peer_key,
        ca_key=ca_key,
        ca_cert=ca_cert,
        peer_name=peer_name,
        days_valid=days_valid,
    )

    if not peer_export_dir.exists():
        peer_export_dir.mkdir(parents=True, exist_ok=True)

    save_private_key_pem(peer_key, peer_key_path, password=None)
    save_cert_pem(peer_cert, peer_cert_path)

    print("       cert:", peer_cert_path)
    print("       key :", peer_key_path)

    return peer_cert_path, peer_key_path


def install_runtime_files(
    project_root: Path,
    ca_export_path: Path,
    peer_cert_export: Path,
    peer_key_export: Path,
) -> tuple[Path, Path, Path]:
    tls_dir = project_root / "tls"
    if not tls_dir.exists():
        tls_dir.mkdir(parents=True, exist_ok=True)

    runtime_ca_path = tls_dir / "ca_root.crt"
    runtime_cert_path = tls_dir / "peer_cert.pem"
    runtime_key_path = tls_dir / "peer_key.pem"

    with ca_export_path.open("rb") as src:
        ca_bytes = src.read()
    with runtime_ca_path.open("wb") as dst:
        dst.write(ca_bytes)

    with peer_cert_export.open("rb") as src:
        cert_bytes = src.read()
    with runtime_cert_path.open("wb") as dst:
        dst.write(cert_bytes)

    with peer_key_export.open("rb") as src:
        key_bytes = src.read()
    with runtime_key_path.open("wb") as dst:
        dst.write(key_bytes)

    try:
        os.chmod(runtime_ca_path, 0o644)
    except PermissionError:
        print("[WARN] Could not chmod ca_root.crt")

    try:
        os.chmod(runtime_cert_path, 0o644)
    except PermissionError:
        print("[WARN] Could not chmod peer_cert.pem")

    try:
        os.chmod(runtime_key_path, 0o600)
    except PermissionError:
        print("[WARN] Could not chmod peer_key.pem")

    print("[RUNTIME] Installed TLS runtime files into ./tls")
    print("          CA_FILE =", runtime_ca_path)
    print("          CERTI   =", runtime_cert_path)
    print("          KEY     =", runtime_key_path)

    return runtime_ca_path, runtime_cert_path, runtime_key_path


def main() -> None:
    project_root = get_project_root()
    print("[INFO] Project root:", project_root)

    ca_storage_dir = project_root / "pkica"
    export_base_dir = project_root / "pkica_export"
    export_ca_dir = export_base_dir / "ca"
    peers_export_base = export_base_dir / "peers"

    username = getpass.getuser()
    peer_name = username + ".lanfx.local"
    print("[INFO] Local username:", username)
    print("[INFO] Peer name     :", peer_name)

    ca_export_path, ca_key, ca_cert = init_or_load_ca(
        ca_storage_dir=ca_storage_dir,
        export_ca_dir=export_ca_dir,
    )

    peer_cert_export, peer_key_export = init_or_load_peer(
        ca_key=ca_key,
        ca_cert=ca_cert,
        peers_export_base=peers_export_base,
        peer_name=peer_name,
        days_valid=825,
    )

    runtime_ca_path, runtime_cert_path, runtime_key_path = install_runtime_files(
        project_root=project_root,
        ca_export_path=ca_export_path,
        peer_cert_export=peer_cert_export,
        peer_key_export=peer_key_export,
    )

    print()
    print("[ENV] Suggested .env entries for this node:")
    print(f"      CERTI='{runtime_cert_path}'")
    print(f"      KEY='{runtime_key_path}'")
    print(f"      CA_FILE='{runtime_ca_path}'")
    print(f"      SERVER_NAME='{peer_name}'")
    print("      # RECIVHOST, DEST_HOST, PORT as before")


if __name__ == "__main__":
    main()
