#!/usr/bin/env python3
"""
Smoke test for all crypto-related packages on the current architecture.

Run:  python test_crypto_imports.py

Tests:
  1. Core imports (cryptography, pyOpenSSL, ownca, aioquic, paramiko)
  2. bcrypt or fallback
  3. X.509 certificate generation round-trip
  4. Architecture detection
"""

import sys
import struct

BITS = struct.calcsize("P") * 8
RESULTS = []


def test(name, fn):
    """Run a test function, record pass/fail."""
    try:
        result = fn()
        RESULTS.append((name, True, result))
        print(f"  ✓ {name}: {result}")
    except Exception as e:
        RESULTS.append((name, False, str(e)))
        print(f"  ✗ {name}: {e}")


def main():
    print(f"\n{'='*50}")
    print(f"  LANFXplorer Crypto Smoke Test ({BITS}-bit)")
    print(f"  Python {sys.version}")
    print(f"{'='*50}\n")

    # --- Core imports ---
    print("[1] Core Package Imports")

    def test_cryptography():
        import cryptography
        return f"cryptography {cryptography.__version__}"
    test("cryptography", test_cryptography)

    def test_pyopenssl():
        import OpenSSL
        return f"pyOpenSSL {OpenSSL.__version__}"
    test("pyOpenSSL", test_pyopenssl)

    def test_ownca():
        from ownca import CertificateAuthority
        return "ownca OK"
    test("ownca", test_ownca)

    def test_aioquic():
        import aioquic
        return f"aioquic {aioquic.__version__}"
    test("aioquic", test_aioquic)

    def test_paramiko():
        import paramiko
        return f"paramiko {paramiko.__version__}"
    test("paramiko", test_paramiko)

    # --- bcrypt / fallback ---
    print("\n[2] bcrypt / Compatibility Layer")

    def test_bcrypt_compat():
        # Try importing from this package's bcrypt_compat module
        try:
            from bcrypt_compat import (
                hashpw, checkpw, gensalt,
                is_using_fallback, backend_name
            )
        except ImportError:
            # Fallback: try direct bcrypt
            import bcrypt
            return f"bcrypt {bcrypt.__version__} (direct import)"

        pw = b"smoketest"
        salt = gensalt()
        hashed = hashpw(pw, salt)
        assert checkpw(pw, hashed), "Password verification failed!"
        assert not checkpw(b"wrong", hashed), "Wrong password should not verify!"
        return f"{backend_name()} — verify OK"
    test("bcrypt/compat", test_bcrypt_compat)

    # --- X.509 round-trip ---
    print("\n[3] X.509 Certificate Generation")

    def test_x509():
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        import datetime

        # Generate EC key
        key = ec.generate_private_key(ec.SECP256R1())

        # Self-signed cert
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "test.lanfxplorer.local"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256())
        )

        # Serialize round-trip
        pem = cert.public_bytes(serialization.Encoding.PEM)
        loaded = x509.load_pem_x509_certificate(pem)
        cn = loaded.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        return f"CN={cn}, serial={cert.serial_number}"
    test("x509 gen + load", test_x509)

    # --- Arch detection ---
    print("\n[4] Architecture Detection")

    def test_arch():
        from arch_config import ARCH, PY_VERSION, BITS as ABITS, summary
        return f"{ARCH} ({ABITS}-bit), Python target={PY_VERSION}"
    test("arch_config", test_arch)

    # --- Summary ---
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{'='*50}")
    print(f"  Results: {passed}/{total} passed")
    if passed == total:
        print("  ✓ All tests passed!")
    else:
        print("  ✗ Some tests failed — review output above")
        for name, ok, info in RESULTS:
            if not ok:
                print(f"    FAIL: {name} — {info}")
    print(f"{'='*50}\n")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
