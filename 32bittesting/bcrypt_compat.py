"""
bcrypt compatibility layer for 32-bit systems.

On 64-bit: uses real bcrypt (native C extension with pre-built wheel).
On 32-bit: falls back to hashlib.pbkdf2_hmac (stdlib, no native deps).

Drop-in replacement for pki/store.py — swap the import:
    # OLD:  import bcrypt
    # NEW:  from bcrypt_compat import hashpw, checkpw, gensalt

The fallback produces a different hash format ($pbkdf2$ prefix) so
32-bit and 64-bit hashes are NOT cross-compatible. This is acceptable
for per-device peer stores that don't sync passwords across architectures.
"""

import hashlib
import os
import base64
import struct

try:
    import bcrypt as _bcrypt
    _HAS_BCRYPT = True
except ImportError:
    _bcrypt = None
    _HAS_BCRYPT = False


# ─── Fallback constants ──────────────────────────────────
_PBKDF2_ITERATIONS = 600_000  # OWASP 2023 recommendation for SHA-256
_SALT_LENGTH = 16
_HASH_PREFIX = b"$pbkdf2$"


def _pbkdf2_hash(password: bytes, salt: bytes) -> bytes:
    """Hash password using PBKDF2-HMAC-SHA256."""
    dk = hashlib.pbkdf2_hmac("sha256", password, salt, _PBKDF2_ITERATIONS)
    # Encode as:  $pbkdf2$<iterations>$<b64salt>$<b64hash>
    return (
        _HASH_PREFIX
        + str(_PBKDF2_ITERATIONS).encode()
        + b"$"
        + base64.b64encode(salt)
        + b"$"
        + base64.b64encode(dk)
    )


def _pbkdf2_check(password: bytes, hashed: bytes) -> bool:
    """Verify password against a PBKDF2 hash."""
    if not hashed.startswith(_HASH_PREFIX):
        return False
    parts = hashed[len(_HASH_PREFIX):].split(b"$")
    if len(parts) != 3:
        return False
    iterations = int(parts[0])
    salt = base64.b64decode(parts[1])
    stored_dk = base64.b64decode(parts[2])

    dk = hashlib.pbkdf2_hmac("sha256", password, salt, iterations)
    # Constant-time comparison
    return hmac_compare(dk, stored_dk)


def hmac_compare(a: bytes, b: bytes) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    import hmac
    return hmac.compare_digest(a, b)


# ─── Public API (matches bcrypt interface) ────────────────

def gensalt(rounds: int = 12) -> bytes:
    """Generate a salt.

    On 64-bit (real bcrypt): returns bcrypt salt with specified rounds.
    On 32-bit (fallback):    returns random bytes (rounds param ignored).
    """
    if _HAS_BCRYPT:
        return _bcrypt.gensalt(rounds=rounds)
    return os.urandom(_SALT_LENGTH)


def hashpw(password: bytes, salt: bytes) -> bytes:
    """Hash a password.

    On 64-bit (real bcrypt): bcrypt.hashpw(password, salt).
    On 32-bit (fallback):    PBKDF2-HMAC-SHA256.
    """
    if _HAS_BCRYPT:
        return _bcrypt.hashpw(password, salt)
    return _pbkdf2_hash(password, salt)


def checkpw(password: bytes, hashed_password: bytes) -> bool:
    """Verify a password against its hash.

    On 64-bit (real bcrypt): bcrypt.checkpw(password, hashed_password).
    On 32-bit (fallback):    verifies PBKDF2-HMAC-SHA256 hash.
    """
    if _HAS_BCRYPT:
        return _bcrypt.checkpw(password, hashed_password)
    return _pbkdf2_check(password, hashed_password)


def is_using_fallback() -> bool:
    """Return True if using PBKDF2 fallback instead of real bcrypt."""
    return not _HAS_BCRYPT


def backend_name() -> str:
    """Return name of the active hashing backend."""
    if _HAS_BCRYPT:
        return f"bcrypt {_bcrypt.__version__}"
    return f"pbkdf2_hmac (sha256, {_PBKDF2_ITERATIONS} iterations)"


if __name__ == "__main__":
    # Self-test
    print(f"Backend: {backend_name()}")
    print(f"Using fallback: {is_using_fallback()}")

    test_pw = b"testpassword123"
    salt = gensalt()
    hashed = hashpw(test_pw, salt)

    print(f"Hash: {hashed}")
    print(f"Verify (correct):  {checkpw(test_pw, hashed)}")
    print(f"Verify (wrong):    {checkpw(b'wrongpassword', hashed)}")

    assert checkpw(test_pw, hashed) is True
    assert checkpw(b"wrongpassword", hashed) is False
    print("✓ All bcrypt_compat self-tests passed")
