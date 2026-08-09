"""
CA Discovery, Signing Server, and Certificate Management.

Security fixes applied:
  Fix 4.1  — TOFU CA pinning via PeerStore.__ca__
  Fix 4.2  — Verify received CA fingerprint against pin BEFORE sending CSR
  Fix 4.4  — Persistent enrollment token guards CSR signing
  Fix 4.5  — ca_key.pem stored at chmod 0600 (default); optional keyring via --use-keyring
  Fix 4.6  — Enrollment token protected by HMAC challenge-response (token never crosses wire)
  Fix 4.7  — CA split-brain prevention via UUID election protocol
  Fix 4.8  — CA cert validity 10 years, client cert 90 days (in pki/utils.py)
"""

import asyncio
import hashlib
import hmac as _hmac
import os
import platform
import secrets
import socket
import logging
import json
import sys
from pathlib import Path
from typing import Optional, Tuple

# Add parent directory to path for app_config import
_pki_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(_pki_dir.parent))

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from pki import utils
from pki.utils import CA_CERT_VALIDITY_DAYS, CLIENT_CERT_VALIDITY_DAYS
from app_config import AppConfig

# Use centralized constants from AppConfig
DISCOVERY_PORT   = AppConfig.CA_DISCOVERY_PORT
SIGNING_PORT     = AppConfig.CA_SIGNING_PORT
DISCOVERY_MSG    = AppConfig.CA_DISCOVERY_MSG
CA_RESPONSE_PREFIX = AppConfig.CA_RESPONSE_PREFIX

# ── Election protocol messages ────────────────────────────────────────────────
# Fix 4.7: broadcast before becoming CA; lowest UUID wins
_ELECTION_PREFIX = b"I_WANT_CA "
_ELECTION_WINDOW = 1.8   # seconds to collect competing candidates

logger = logging.getLogger(__name__)


# ── SecurityError ─────────────────────────────────────────────────────────────

class SecurityError(Exception):
    """Raised when a security invariant is violated (e.g. CA fingerprint mismatch)."""


# ─────────────────────────────────────────────────────────────────────────────
# Discovery protocol (unchanged except election message awareness)
# ─────────────────────────────────────────────────────────────────────────────

class CADiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, is_ca: bool, ca_manager):
        self.is_ca = is_ca
        self.ca_manager = ca_manager
        self.transport = None
        self._broadcast_handle = None

    def connection_made(self, transport):
        self.transport = transport
        if not self.is_ca:
            sock = self.transport.get_extra_info('socket')
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._send_broadcast()

    def _send_broadcast(self):
        """Send WHO_IS_CA and reschedule until CA is found or transport closes."""
        if self.transport and not self.transport.is_closing():
            try:
                config = AppConfig()
                target_broadcast = config.broadcast or '<broadcast>'
                self.transport.sendto(DISCOVERY_MSG, (target_broadcast, DISCOVERY_PORT))
                print(f"[CA discovery] WHO_IS_CA → {target_broadcast}:{DISCOVERY_PORT} (via {self.ca_manager.host})")
            except Exception as e:
                print(f"[CA discovery] Broadcast failed: {e}")
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
            self._broadcast_handle = loop.call_later(2.0, self._send_broadcast)

    def connection_lost(self, exc):
        if self._broadcast_handle:
            self._broadcast_handle.cancel()
            self._broadcast_handle = None

    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        if self.is_ca and data == DISCOVERY_MSG:
            response = f"{CA_RESPONSE_PREFIX.decode()} {self.ca_manager.host} {SIGNING_PORT}".encode()
            self.transport.sendto(response, addr)
            print(f"[CA discovery] Replied I_AM_CA to {addr[0]}")
        elif not self.is_ca and data.startswith(CA_RESPONSE_PREFIX):
            parts = data.decode().split()
            if len(parts) >= 3:
                ca_host = parts[1]
                ca_port = int(parts[2])
                print(f"[CA discovery] Received I_AM_CA from {ca_host}:{ca_port}")
                if self._broadcast_handle:
                    self._broadcast_handle.cancel()
                    self._broadcast_handle = None
                asyncio.create_task(self.ca_manager.on_ca_found(ca_host, ca_port))
        # Fix 4.7: collect election candidates
        elif data.startswith(_ELECTION_PREFIX):
            try:
                candidate_uuid = data[len(_ELECTION_PREFIX):].decode().strip()
                self.ca_manager._election_candidates.add(candidate_uuid)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# CA Signing Server  (Fix 4.4 + 4.6 — enrollment token + HMAC challenge)
# ─────────────────────────────────────────────────────────────────────────────

class CASigningServer:
    """TCP server that signs CSRs for enrolled peers.

    Protocol (Fix 4.4 + 4.6):
      1. Server sends: CA cert PEM  [4B len][PEM]
      2. Server sends: 32-byte random nonce  [4B len][nonce bytes]
      3. Client sends: HMAC-SHA256(enrollment_token, nonce)  [4B len][32 bytes]
      4. If HMAC valid → Client sends CSR  [4B len][CSR PEM]
      5. Server sends: signed cert  [4B len][cert PEM]
      6. If HMAC invalid → Server sends: error  [4B len][b"ENROLL_FAIL"]

    This ensures the enrollment token NEVER crosses the wire — only
    HMAC(token, nonce) does, so sniffing the exchange gives the attacker nothing.
    """

    def __init__(self, ca_cert_pem: bytes, ca_key_pem: bytes, peer_store):
        self.ca_cert_pem = ca_cert_pem
        self.ca_key_pem  = ca_key_pem
        self._store      = peer_store   # PeerStore instance

    async def handle_client(self, reader, writer):
        peer = writer.get_extra_info('peername')
        try:
            # ── Step 1: Send CA cert ──────────────────────────────────────────
            cert_len = len(self.ca_cert_pem)
            writer.write(cert_len.to_bytes(4, 'big'))
            writer.write(self.ca_cert_pem)
            await writer.drain()

            # ── Step 2: Send nonce for HMAC challenge ─────────────────────────
            nonce = secrets.token_bytes(32)
            writer.write(len(nonce).to_bytes(4, 'big'))
            writer.write(nonce)
            await writer.drain()

            # ── Step 3: Read client HMAC response ────────────────────────────
            hmac_len_bytes = await reader.readexactly(4)
            hmac_len = int.from_bytes(hmac_len_bytes, 'big')
            if hmac_len != 32:
                writer.write((13).to_bytes(4, 'big'))
                writer.write(b"ENROLL_FAIL")
                await writer.drain()
                logger.warning(f"[CA] Enrollment rejected: bad HMAC length from {peer}")
                return
            client_hmac = await reader.readexactly(hmac_len)

            # Compute expected HMAC using stored enrollment token
            token = self._store.get_or_create_enrollment_token()
            expected_hmac = _hmac.new(
                token.encode(), nonce, hashlib.sha256
            ).digest()

            if not _hmac.compare_digest(client_hmac, expected_hmac):
                writer.write((11).to_bytes(4, 'big'))
                writer.write(b"ENROLL_FAIL")
                await writer.drain()
                logger.warning(f"[CA] Enrollment rejected: wrong token HMAC from {peer}")
                return

            # ── Step 4: Read CSR ──────────────────────────────────────────────
            csr_len_bytes = await reader.readexactly(4)
            csr_size = int.from_bytes(csr_len_bytes, 'big')
            if csr_size > 65536:
                logger.warning(f"[CA] CSR too large ({csr_size} bytes) from {peer}")
                return
            csr_pem = await reader.readexactly(csr_size)

            # ── Step 5: Sign and return ───────────────────────────────────────
            client_cert = utils.sign_csr(csr_pem, self.ca_cert_pem, self.ca_key_pem)
            writer.write(len(client_cert).to_bytes(4, 'big'))
            writer.write(client_cert)
            await writer.drain()
            logger.info(f"[CA] Signed cert for {peer}")

        except Exception as e:
            logger.error(f"[CA] Signing error from {peer}: {e}")
        finally:
            writer.close()
            await writer.wait_closed()


# ─────────────────────────────────────────────────────────────────────────────
# CA Manager
# ─────────────────────────────────────────────────────────────────────────────

class CAManager:
    def __init__(self, host: str, cert_dir: str):
        self.host = host
        self.cert_dir = cert_dir
        self.ca_found_event  = asyncio.Event()
        self.is_ca           = False
        self.ca_info         = None
        self.discovery_transport = None
        # Fix 4.7: set of UUIDs collected during election window
        self._election_candidates: set = set()

    # ── Discovery ─────────────────────────────────────────────────────────────

    async def start_discovery(self):
        """Start CA discovery UDP socket, locked to the correct interface."""
        import socket as _socket

        loop = asyncio.get_running_loop()

        sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_BROADCAST, 1)

        if platform.system().lower() != "windows":
            try:
                sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass
            try:
                from app_config import get_config as _get_config
                cfg = _get_config()
                iface = cfg.interface
                if iface:
                    sock.setsockopt(
                        _socket.SOL_SOCKET,
                        _socket.SO_BINDTODEVICE,
                        (iface + '\0').encode()
                    )
                    logger.info(f"CA discovery socket bound to device {iface}")
            except (AttributeError, OSError, PermissionError) as e:
                print(f"[CA discovery] SO_BINDTODEVICE unavailable ({e}), falling back to 0.0.0.0")

        sock.bind(('0.0.0.0', DISCOVERY_PORT))

        self.discovery_transport, _ = await loop.create_datagram_endpoint(
            lambda: CADiscoveryProtocol(self.is_ca, self),
            sock=sock,
        )
        logger.info(f"Discovery started on port {DISCOVERY_PORT} (host={self.host})")

    def stop_discovery(self):
        if self.discovery_transport:
            self.discovery_transport.close()

    async def on_ca_found(self, host: str, port: int):
        if not self.ca_found_event.is_set():
            self.ca_info = (host, port)
            self.ca_found_event.set()

    # ── Fix 4.7: CA election ──────────────────────────────────────────────────

    async def _elect_ca(self) -> bool:
        """Broadcast candidacy and return True if this node wins the election.

        Algorithm: lowest UUID wins — deterministic, no coordination required.
        Election window is _ELECTION_WINDOW seconds, adding negligible startup delay.

        This prevents split-brain when two nodes simultaneously discover no CA
        and both try to become CA at the same time.
        """
        from pki.store import PeerStore
        store = PeerStore(os.path.join(self.cert_dir, "..", "pkica_export", "peers.json"))
        my_uuid = store.get_or_create_node_uuid()

        # Broadcast candidacy on the discovery port so peers can collect it
        import socket as _socket
        try:
            config = AppConfig()
            broadcast_addr = config.broadcast or '<broadcast>'
            sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_BROADCAST, 1)
            msg = _ELECTION_PREFIX + my_uuid.encode()
            sock.sendto(msg, (broadcast_addr, DISCOVERY_PORT))
            sock.close()
            print(f"[CA election] Broadcast candidacy: {my_uuid}")
        except Exception as exc:
            print(f"[CA election] Could not broadcast candidacy: {exc}")

        # Wait for election window — collect other candidates
        await asyncio.sleep(_ELECTION_WINDOW)

        all_candidates = self._election_candidates | {my_uuid}
        winner = min(all_candidates)
        i_win = (winner == my_uuid)
        print(f"[CA election] Candidates={sorted(all_candidates)} → winner={winner} {'(me)' if i_win else '(not me)'}")
        return i_win

    # ── become_ca (Fix 4.5, 4.7, 4.8) ────────────────────────────────────────

    async def become_ca(self):
        """Run election, then generate CA key + cert if we win.

        Fix 4.5: ca_key.pem is written with chmod 0600.
        Fix 4.7: election protocol runs first.
        Fix 4.8: CA cert validity is CA_CERT_VALIDITY_DAYS (10 years).
        """
        # ── Election (Fix 4.7) ────────────────────────────────────────────────
        i_win = await self._elect_ca()
        if not i_win:
            print("[CA election] Lost election — waiting for winner to become CA...")
            # Wait for the winner to announce I_AM_CA
            try:
                await asyncio.wait_for(self.ca_found_event.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                print("[CA election] WARNING: election winner did not announce in time. Retrying discovery.")
            return None, None

        logger.info("Won CA election. Becoming CA...")
        self.is_ca = True
        self.stop_discovery()

        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography import x509 as _x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        import datetime

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        subject = _x509.Name([
            _x509.NameAttribute(NameOID.COMMON_NAME, "LAN CA"),
        ])
        cert = _x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            subject
        ).public_key(
            key.public_key()
        ).serial_number(
            _x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.now(datetime.timezone.utc)
        ).not_valid_after(
            # Fix 4.8: 10-year CA cert
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=CA_CERT_VALIDITY_DAYS)
        ).add_extension(
            _x509.BasicConstraints(ca=True, path_length=None), critical=True,
        ).sign(key, hashes.SHA256())

        ca_cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        ca_key_pem  = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )

        # Fix 4.5: Write CA key with 0600 permissions
        ca_cert_path = os.path.join(self.cert_dir, "ca_cert.pem")
        ca_key_path  = os.path.join(self.cert_dir, "ca_key.pem")

        with open(ca_cert_path, "wb") as f:
            f.write(ca_cert_pem)

        with open(ca_key_path, "wb") as f:
            f.write(ca_key_pem)
        try:
            os.chmod(ca_key_path, 0o600)
            print(f"[CA] ca_key.pem written at 0600 — this is your network's root of trust. Protect it.")
        except Exception as exc:
            print(f"[CA] WARNING: Could not chmod ca_key.pem: {exc}")

        # Initialise PeerStore so enrollment token is created on first CA boot
        from pki.store import PeerStore
        store = PeerStore(os.path.join(self.cert_dir, "..", "pkica_export", "peers.json"))
        token = store.get_or_create_enrollment_token()
        print(f"\n{'='*60}")
        print(f"  CA Enrollment Token: {token}")
        print(f"  New peers must use this token to enroll.")
        print(f"  Keep this secret within your trusted group.")
        print(f"{'='*60}\n")

        _start_server_kwargs = {"reuse_address": True}
        if platform.system().lower() != "windows":
            _start_server_kwargs["reuse_port"] = True

        server = CASigningServer(ca_cert_pem, ca_key_pem, store)
        await asyncio.start_server(
            server.handle_client, '0.0.0.0', SIGNING_PORT,
            **_start_server_kwargs
        )
        logger.info(f"CA Signing Server started on port {SIGNING_PORT}")

        await self.start_discovery()
        return ca_cert_pem, ca_key_pem

    # ── check / probe ─────────────────────────────────────────────────────────

    def check_ca_status(self) -> bool:
        """Check if CA keys exist on disk and update is_ca state.

        NOTE: Only checks local disk. Use probe_ca_on_network() to verify no
        other CA is active on the network before assuming the CA role.
        """
        ca_cert_path = os.path.join(self.cert_dir, "ca_cert.pem")
        ca_key_path  = os.path.join(self.cert_dir, "ca_key.pem")
        if os.path.exists(ca_cert_path) and os.path.exists(ca_key_path):
            self.is_ca = True
            return True
        return False

    async def probe_ca_on_network(self, timeout: float = 3.0):
        """Send one WHO_IS_CA broadcast and wait up to *timeout* seconds.

        Returns (host, port) or None.
        """
        import socket as _socket

        config = AppConfig()
        broadcast_addr = config.broadcast or "<broadcast>"

        future    = asyncio.get_running_loop().create_future()
        transport = None

        class _ProbeProtocol(asyncio.DatagramProtocol):
            def connection_made(self, t):
                nonlocal transport
                transport = t
                sock = t.get_extra_info('socket')
                sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_BROADCAST, 1)
                try:
                    t.sendto(DISCOVERY_MSG, (broadcast_addr, DISCOVERY_PORT))
                except Exception as e:
                    if not future.done():
                        future.set_result(None)

            def datagram_received(self, data, addr):
                if data.startswith(CA_RESPONSE_PREFIX) and not future.done():
                    parts = data.decode().split()
                    ca_host = parts[1] if len(parts) >= 3 else addr[0]
                    ca_port = int(parts[2]) if len(parts) >= 3 else SIGNING_PORT
                    print(f"[CA probe] Found existing CA at {ca_host}:{ca_port}")
                    future.set_result((ca_host, ca_port))

            def error_received(self, exc):
                if not future.done():
                    future.set_result(None)

            def connection_lost(self, exc):
                if not future.done():
                    future.set_result(None)

        loop = asyncio.get_running_loop()
        found_ca = None
        try:
            if platform.system().lower() == "windows":
                sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
                sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
                sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_BROADCAST, 1)
                sock.bind(('0.0.0.0', 0))
                _transport, _ = await loop.create_datagram_endpoint(_ProbeProtocol, sock=sock)
            else:
                _transport, _ = await loop.create_datagram_endpoint(
                    _ProbeProtocol,
                    local_addr=('0.0.0.0', 0),
                    allow_broadcast=True)
            try:
                found_ca = await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
            except asyncio.TimeoutError:
                pass
        except Exception as e:
            print(f"[CA probe] Could not open UDP socket: {e}")
        finally:
            if transport and not transport.is_closing():
                transport.close()

        if found_ca is None:
            print("[CA probe] No CA responded on the network.")
        return found_ca

    # ── start_ca_service (Fix 4.5) ────────────────────────────────────────────

    async def start_ca_service(self):
        """Start the CA Signing Server and Discovery Responder.

        Fix 4.5: Verifies ca_key.pem has 0600 permissions at startup.
        """
        if not self.is_ca:
            if not self.check_ca_status():
                logger.warning("Cannot start CA service: CA keys not found.")
                return

        try:
            ca_cert_path = os.path.join(self.cert_dir, "ca_cert.pem")
            ca_key_path  = os.path.join(self.cert_dir, "ca_key.pem")

            # Fix 4.5: warn if key permissions are too open
            try:
                mode = os.stat(ca_key_path).st_mode & 0o777
                if mode & 0o077:   # group/other readable or writable
                    print(f"[CA] WARNING: ca_key.pem has permissions {oct(mode)} — should be 0600. "
                          f"Anyone with filesystem access can sign arbitrary certificates.")
                    os.chmod(ca_key_path, 0o600)
                    print("[CA] Permissions corrected to 0600.")
            except Exception:
                pass

            with open(ca_cert_path, "rb") as f: ca_cert_pem = f.read()
            with open(ca_key_path,  "rb") as f: ca_key_pem  = f.read()

            from pki.store import PeerStore
            store = PeerStore(os.path.join(self.cert_dir, "..", "pkica_export", "peers.json"))
            token = store.get_or_create_enrollment_token()
            print(f"\n[CA] Enrollment Token: {token}  (new peers need this)\n")

            server = CASigningServer(ca_cert_pem, ca_key_pem, store)
            _start_server_kwargs = {"reuse_address": True}
            if platform.system().lower() != "windows":
                _start_server_kwargs["reuse_port"] = True
            self.signing_server = await asyncio.start_server(
                server.handle_client, '0.0.0.0', SIGNING_PORT,
                **_start_server_kwargs
            )
            logger.info(f"CA Signing Server started on port {SIGNING_PORT}")

            await self.start_discovery()

        except Exception as e:
            logger.error(f"Failed to start CA service: {e}")

    # ── get_signed_cert (Fix 4.1, 4.2, 4.6) ──────────────────────────────────

    async def get_signed_cert(
        self,
        private_key_pem: bytes,
        common_name: str,
        enrollment_token: str,
    ) -> Tuple[bytes, bytes]:
        """Enroll with the CA and return (client_cert_pem, ca_cert_pem).

        Fix 4.1 — TOFU CA pinning:
          * First call: CA fingerprint is stored (Trust-On-First-Use).
          * Subsequent calls: fingerprint must match pin or enrollment aborts.
          Issue 10 note: first join is still unauthenticated (same as SSH TOFU).

        Fix 4.2 — Verify CA cert fingerprint BEFORE sending CSR:
          * We never transmit the CSR to a CA whose fingerprint we don't trust.

        Fix 4.6 — HMAC challenge-response:
          * We send HMAC(enrollment_token, nonce) instead of the raw token.
          * The actual token never appears on the wire.
        """
        from pki.store import PeerStore
        store = PeerStore(os.path.join(self.cert_dir, "..", "pkica_export", "peers.json"))

        csr_pem = utils.generate_csr(private_key_pem, common_name, san_ips=[self.host])

        host, port = self.ca_info
        reader, writer = await asyncio.open_connection(host, port)

        try:
            # ── Step 1: Receive CA cert ───────────────────────────────────────
            len_bytes   = await reader.readexactly(4)
            ca_cert_len = int.from_bytes(len_bytes, 'big')
            ca_cert_pem = await reader.readexactly(ca_cert_len)

            # ── Fix 4.1 + 4.2: Verify / pin CA fingerprint ───────────────────
            received_fp = utils.fingerprint_pem(ca_cert_pem)
            pinned      = store.get_trusted_ca()

            if pinned is None:
                # TOFU: first join — trust and pin this CA
                print(f"[CA enroll] TOFU: pinning CA fingerprint {received_fp[:16]}...")
                store.set_trusted_ca(received_fp, ca_cert_pem.decode())
                print("[CA enroll] CA fingerprint pinned. Future connections will verify against this.")
            else:
                if not _hmac.compare_digest(received_fp, pinned["fingerprint"]):
                    # ── ABORT: CA fingerprint changed — possible rogue CA ─────
                    msg = (
                        f"\n{'!'*60}\n"
                        f"  SECURITY WARNING: CA FINGERPRINT MISMATCH\n"
                        f"  Pinned : {pinned['fingerprint']}\n"
                        f"  Received: {received_fp}\n"
                        f"  Enrollment aborted. If you intentionally replaced the CA,\n"
                        f"  run: lanfxplorer --reset-ca-pin\n"
                        f"{'!'*60}\n"
                    )
                    print(msg)
                    logger.error(f"CA fingerprint mismatch — aborting enrollment")
                    raise SecurityError(
                        f"CA fingerprint mismatch: pinned={pinned['fingerprint'][:16]}... "
                        f"received={received_fp[:16]}..."
                    )
                # Fingerprints match — proceed
                print(f"[CA enroll] CA fingerprint verified ✓")

            # ── Fix 4.6: HMAC challenge-response ─────────────────────────────
            # Read nonce sent by CA signing server
            nonce_len_bytes = await reader.readexactly(4)
            nonce_len       = int.from_bytes(nonce_len_bytes, 'big')
            nonce           = await reader.readexactly(nonce_len)

            # Compute HMAC(token, nonce) — token never sent over the wire
            client_hmac = _hmac.new(
                enrollment_token.encode(), nonce, "sha256"
            ).digest()

            writer.write(len(client_hmac).to_bytes(4, 'big'))
            writer.write(client_hmac)
            await writer.drain()

            # ── Step 4: Send CSR ──────────────────────────────────────────────
            writer.write(len(csr_pem).to_bytes(4, 'big'))
            writer.write(csr_pem)
            await writer.drain()

            # ── Step 5: Read signed cert (or ENROLL_FAIL) ─────────────────────
            resp_len_bytes  = await reader.readexactly(4)
            resp_len        = int.from_bytes(resp_len_bytes, 'big')
            resp_data       = await reader.readexactly(resp_len)

            if resp_data in (b"ENROLL_FAIL",):
                raise SecurityError(
                    "CA rejected enrollment token. Check that you are using the correct "
                    "enrollment token shown on the CA node."
                )

            client_cert_pem = resp_data
            return client_cert_pem, ca_cert_pem

        finally:
            writer.close()
            await writer.wait_closed()

