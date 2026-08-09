"""Simple JSON-backed peer store for TOFU decisions.

This stores peers in a JSON file with 0600 permissions. Passwords are hashed
with bcrypt when provided. Certificate PEMs are encrypted at rest using Fernet.

Special keys in the JSON file:
  "__ca__"              — pinned CA fingerprint (TOFU, Fix 4.1)
  "__enrollment_token__" — persistent enrollment token for CSR authorization (Fix 4.4)
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from typing import Dict, Optional

try:
    # 32bitcodes is not a valid package name, so we add it to path to import module directly
    import sys
    import os as _os
    _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    _test_dir = _os.path.join(_root, "32bitcodes")
    if _test_dir not in sys.path:
        sys.path.append(_test_dir)
    import bcrypt_compat
    hashpw = bcrypt_compat.hashpw
    checkpw = bcrypt_compat.checkpw
    gensalt = bcrypt_compat.gensalt
except ImportError:
    # Fallback to standard bcrypt (64-bit / normal install)
    import bcrypt
    hashpw = bcrypt.hashpw
    checkpw = bcrypt.checkpw
    gensalt = bcrypt.gensalt

from cryptography.fernet import Fernet

from .utils import fingerprint_pem, load_cert_pem


class PeerStoreError(Exception):
    pass


# ── Special reserved keys ────────────────────────────────────────────────────
# These are NOT peer fingerprints — they store network-wide PKI metadata.
_KEY_CA              = "__ca__"              # TOFU-pinned CA record
_KEY_ENROLL_TOKEN    = "__enrollment_token__" # persistent enrollment secret


class PeerStore:
    def __init__(self, path: Optional[str] = None):
        self.path = path or os.environ.get("PEERS_FILE") or os.path.join(os.getcwd(), "pkica_export", "peers.json")
        self._lock = threading.Lock()
        self._data: Dict[str, Dict] = {}
        self._encryption_key = self._load_or_create_key()
        self._cipher = Fernet(self._encryption_key)
        self._ensure_file()
        self._load()

    def _load_or_create_key(self) -> bytes:
        """Load or create encryption key for certificate storage."""
        key_file = os.path.join(os.path.dirname(self.path), ".peers_key")
        if os.path.exists(key_file):
            try:
                with open(key_file, "rb") as f:
                    return f.read()
            except Exception:
                pass
        
        # Generate new key
        key = Fernet.generate_key()
        try:
            with open(key_file, "wb") as f:
                f.write(key)
            os.chmod(key_file, 0o600)
        except Exception:
            pass
        return key

    def _ensure_file(self) -> None:
        directory = os.path.dirname(self.path)
        os.makedirs(directory, exist_ok=True)
        if not os.path.exists(self.path):
            with open(self.path, "w") as f:
                json.dump({}, f)
            # Restrict permissions
            try:
                os.chmod(self.path, 0o600)
            except Exception:
                pass

    def _load(self) -> None:
        with self._lock:
            try:
                with open(self.path, "r") as f:
                    data = json.load(f)
                    # Decrypt cert_pem fields for peer records only
                    self._data = {}
                    for key, rec in data.items():
                        if key.startswith("__"):
                            # Reserved metadata keys — stored as-is (no Fernet)
                            self._data[key] = rec
                            continue
                        if rec.get("cert_pem"):
                            try:
                                encrypted = rec["cert_pem"].encode()
                                decrypted = self._cipher.decrypt(encrypted).decode()
                                rec["cert_pem"] = decrypted
                            except Exception:
                                # Already plaintext, corrupted, or wrong key — keep as-is
                                pass
                        self._data[key] = rec
            except (json.JSONDecodeError, FileNotFoundError):
                self._data = {}

    def _save(self) -> None:
        with self._lock:
            # Encrypt cert_pem before saving; skip reserved metadata keys
            data_to_save = {}
            for key, rec in self._data.items():
                if key.startswith("__"):
                    data_to_save[key] = rec
                    continue
                rec_copy = dict(rec)
                if rec_copy.get("cert_pem"):
                    try:
                        encrypted = self._cipher.encrypt(rec_copy["cert_pem"].encode()).decode()
                        rec_copy["cert_pem"] = encrypted
                    except Exception:
                        # If encryption fails, keep plaintext (fallback)
                        pass
                data_to_save[key] = rec_copy
            
            tmp = self.path + ".tmp"
            try:
                with open(tmp, "w") as f:
                    json.dump(data_to_save, f, indent=2)
                os.chmod(tmp, 0o600)
                os.replace(tmp, self.path)
                os.chmod(self.path, 0o600)
            except Exception:
                if os.path.exists(tmp):
                    os.remove(tmp)

    # ── TOFU CA pinning (Fix 4.1) ────────────────────────────────────────────

    def set_trusted_ca(self, fingerprint: str, cert_pem: str) -> None:
        """Pin the CA fingerprint on first use (TOFU).

        Once set, any CA responding with a different fingerprint is rejected
        by get_signed_cert() — this closes the rogue-CA attack window after
        first join (issue 1 / 8).

        Note: First join is still unauthenticated (TOFU inherits SSH's
        limitation). This only prevents rogue CAs on subsequent joins.
        """
        self._data[_KEY_CA] = {
            "fingerprint": fingerprint.lower(),
            "cert_pem":    cert_pem if isinstance(cert_pem, str) else cert_pem.decode(),
            "pinned_at":   int(time.time()),
        }
        self._save()

    def get_trusted_ca(self) -> Optional[Dict]:
        """Return the pinned CA record, or None if no CA has been trusted yet."""
        return self._data.get(_KEY_CA)

    def clear_trusted_ca(self) -> None:
        """Remove CA pin (use with extreme caution — re-enables TOFU window)."""
        self._data.pop(_KEY_CA, None)
        self._save()

    # ── Enrollment token (Fix 4.4) ───────────────────────────────────────────

    def get_or_create_enrollment_token(self) -> str:
        """Return the persistent enrollment token, creating it once if absent.

        The token is generated once when the CA is first created and never
        regenerated automatically — CA restarts do NOT change it.
        Only manual rotation (clear_enrollment_token + this call) changes it.
        """
        rec = self._data.get(_KEY_ENROLL_TOKEN)
        if rec and rec.get("token"):
            return rec["token"]
        # Generate a new 8-character alphanumeric token (easy to type / display)
        token = secrets.token_hex(4).upper()   # e.g. "A3F2B1C9"
        self._data[_KEY_ENROLL_TOKEN] = {
            "token":      token,
            "created_at": int(time.time()),
        }
        self._save()
        return token

    def verify_enrollment_token(self, candidate: str) -> bool:
        """Return True if *candidate* matches the stored enrollment token."""
        import hmac as _hmac
        rec = self._data.get(_KEY_ENROLL_TOKEN)
        if not rec or not rec.get("token"):
            return False
        return _hmac.compare_digest(candidate.strip().upper(), rec["token"])

    def clear_enrollment_token(self) -> None:
        """Delete the enrollment token (forces regeneration on next call)."""
        self._data.pop(_KEY_ENROLL_TOKEN, None)
        self._save()

    # ── Stable node UUID for CA election (Fix 4.7) ──────────────────────────

    def get_or_create_node_uuid(self) -> str:
        """Return a stable UUID for this node, generating it once if absent.

        Used by the CA election protocol to deterministically pick a winner
        when multiple nodes simultaneously try to become CA.
        """
        import uuid as _uuid
        KEY = "__node_uuid__"
        rec = self._data.get(KEY)
        if rec and rec.get("uuid"):
            return rec["uuid"]
        node_id = str(_uuid.uuid4())
        self._data[KEY] = {"uuid": node_id, "created_at": int(time.time())}
        self._save()
        return node_id

    # ── Peer CRUD ────────────────────────────────────────────────────────────

    def list_peers(self) -> Dict[str, Dict]:
        """Return all peer records, excluding reserved metadata keys."""
        return {k: v for k, v in self._data.items() if not k.startswith("__")}

    def get_peer(self, fingerprint: str) -> Optional[Dict]:
        return self._data.get(fingerprint.lower())

    def add_pending(self, cert_pem: str, note: Optional[str] = None) -> str:
        fp = fingerprint_pem(cert_pem)
        now = int(time.time())
        if fp in self._data:
            return fp

        self._data[fp] = {
            "fingerprint": fp,
            "cert_pem": cert_pem if isinstance(cert_pem, str) else cert_pem.decode("utf-8"),
            "status": "pending",
            "added_at": now,
            "password_hash": None,
            "note": note,
        }
        self._save()
        return fp

    def approve_peer(self, fingerprint: str, password: Optional[str] = None) -> None:
        fp = fingerprint.lower()
        if fp not in self._data:
            raise PeerStoreError("peer not found")
        self._data[fp]["status"] = "trusted"
        if password:
            self.set_password(fp, password)
        self._save()

    def reject_peer(self, fingerprint: str) -> None:
        fp = fingerprint.lower()
        if fp not in self._data:
            raise PeerStoreError("peer not found")
        self._data[fp]["status"] = "rejected"
        self._data[fp]["rejected_at"] = int(time.time())
        self._save()

    def revoke_peer(self, fingerprint: str) -> None:
        """Revoke a previously trusted peer.

        Revoked peers are blocked at the handshake layer (Fix 4.3 — enforced
        in _AuthHandler.handle() in handshake.py).
        """
        fp = fingerprint.lower()
        if fp not in self._data:
            raise PeerStoreError("peer not found")
        self._data[fp]["status"] = "revoked"
        self._data[fp]["revoked_at"] = int(time.time())
        self._save()

    def is_revoked(self, fingerprint: str) -> bool:
        """Return True if the peer is explicitly revoked."""
        fp = fingerprint.lower()
        rec = self._data.get(fp)
        return rec is not None and rec.get("status") == "revoked"

    def set_password(self, fingerprint: str, password: str) -> None:
        fp = fingerprint.lower()
        if fp not in self._data:
            raise PeerStoreError("peer not found")
        hashed = hashpw(password.encode("utf-8"), gensalt())
        self._data[fp]["password_hash"] = hashed.decode("utf-8")
        self._save()

    def verify_password(self, fingerprint: str, password: str) -> bool:
        fp = fingerprint.lower()
        rec = self._data.get(fp)
        if not rec or not rec.get("password_hash"):
            return False
        try:
            return checkpw(password.encode("utf-8"), rec["password_hash"].encode("utf-8"))
        except Exception:
            return False
