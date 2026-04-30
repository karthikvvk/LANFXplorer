#!/usr/bin/env python3
"""
LANFXplorer — Dev Script: Generate CA + Server/Client Certs

Generates a local test CA and signs server + client certs for development.
All crypto via the `cryptography` lib — no aioquic, no system openssl needed.

Usage:
    python3 scripts/make_ca_and_certs.py
    # Certs are written to a temp directory; path printed on stdout.
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
import ipaddress
import sys

# Ensure project root is on sys.path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from cryptography import x509
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def make_ca_and_certs(tmpdir):
    ca_path = os.environ.get("CA_CERT")

    if ca_path and os.path.exists(ca_path):
        raise RuntimeError(
            "CA already exists. Refusing to generate a new CA. "
            "This would fork the trust domain."
        )
    # create CA
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"Test CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    # server cert
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"localhost")])
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(u"localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    # client cert
    client_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"client")])
    client_cert = (
        x509.CertificateBuilder()
        .subject_name(client_name)
        .issuer_name(ca_name)
        .public_key(client_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .sign(ca_key, hashes.SHA256())
    )

    ca_p          = os.path.join(tmpdir, "ca.pem")
    server_p      = os.path.join(tmpdir, "server.pem")
    server_key_p  = os.path.join(tmpdir, "server-key.pem")
    client_p      = os.path.join(tmpdir, "client.pem")
    client_key_p  = os.path.join(tmpdir, "client-key.pem")

    with open(ca_p, "wb") as f:
        f.write(ca_cert.public_bytes(serialization.Encoding.PEM))
    with open(server_p, "wb") as f:
        f.write(server_cert.public_bytes(serialization.Encoding.PEM))
    with open(server_key_p, "wb") as f:
        f.write(server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()))
    with open(client_p, "wb") as f:
        f.write(client_cert.public_bytes(serialization.Encoding.PEM))
    with open(client_key_p, "wb") as f:
        f.write(client_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()))

    return ca_p, server_p, server_key_p, client_p, client_key_p


if __name__ == "__main__":
    tmpdir = tempfile.mkdtemp()
    ca_p, server_p, server_key_p, client_p, client_key_p = make_ca_and_certs(tmpdir)
    print(f"[✓] Certs written to: {tmpdir}")
    print(f"    CA         : {ca_p}")
    print(f"    Server cert: {server_p}")
    print(f"    Server key : {server_key_p}")
    print(f"    Client cert: {client_p}")
    print(f"    Client key : {client_key_p}")
