"""
P2P Handshake — pure TCP auth on port 4437.

Password auth runs over a dedicated TCP server (port 4437, threaded) so
that blocking keyring / D-Bus calls never touch the asyncio event loop used
by the QUIC stack.  File transfers use QUIC exclusively; auth never touches UDP.

Public API
----------
HandshakeService(host, port=4437)       – threaded TCP auth server
    start()    → starts the server in a daemon thread
    stop()     → graceful shutdown

start_handshake_service(host, cert_path, ca_cert_path, port=4437)
    Convenience coroutine — starts service and returns service object.

tcp_handshake(dest_host, password, ...)
    Authenticate a remote peer via a plain TCP connection to port 4437.
    The sender opens the connection and sends the password; the receiver
    verifies and replies AUTH_OK or AUTH_FAIL. No QUIC / UDP involved.

quic_handshake → backward-compat alias for tcp_handshake.
"""

import asyncio
import json
import logging
import os
import socket
import socketserver
import struct
import sys
import threading
from pathlib import Path
from typing import Optional

_pki_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(_pki_dir.parent))

from pki.store import PeerStore
from pki.utils import fingerprint_pem, verify_cert_validity
from app_config import AppConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Wire-format helpers
#
# TWO on-wire formats are supported so that older peer builds interoperate:
#
#   LEGACY  (older VM builds)
#     [2 bytes magic b"P="] [2 bytes big-endian uint16 length] [JSON body]
#
#   NEW  (this build and later)
#     [4 bytes big-endian uint32 length] [JSON body]
#
# _read_json_from_sock() auto-detects which format is incoming.
# _encode_json_legacy() is used for all outgoing frames so that old peers
# can always parse our responses — new peers accept both formats anyway.
# ---------------------------------------------------------------------------

_LEGACY_MAGIC = b"P="  # 0x50 0x3D  — first 2 bytes of legacy frames


def _encode_json_legacy(obj: dict) -> bytes:
    """Encode using the LEGACY wire format: magic 'P=' + uint16 length + JSON."""
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    if len(body) > 65535:
        raise ValueError(f"Auth payload too large for legacy uint16 length: {len(body)}")
    return _LEGACY_MAGIC + struct.pack("!H", len(body)) + body


def _encode_json(obj: dict) -> bytes:
    """Encode using the NEW wire format: uint32 length + JSON."""
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    return struct.pack("!I", len(body)) + body


def _read_json_from_sock(sock: socket.socket) -> dict:
    """
    Read a length-prefixed JSON frame, auto-detecting legacy vs new format.

    Legacy: first 2 bytes == b'P=' → read 2-byte uint16 length, then body.
    New:    any other first 2 bytes  → combine with next 2 bytes as 4-byte
            big-endian uint32 length, then body.
    """
    first2 = _recv_exact(sock, 2)
    if first2 == _LEGACY_MAGIC:
        # Legacy format: 2-byte uint16 length follows the magic
        raw_len = _recv_exact(sock, 2)
        (length,) = struct.unpack("!H", raw_len)
    else:
        # New format: first2 are the top 2 bytes of a 4-byte uint32 length
        rest2 = _recv_exact(sock, 2)
        (length,) = struct.unpack("!I", first2 + rest2)
        if length > 1024 * 1024:
            raise ValueError(f"Auth frame too large: {length}")
    body = _recv_exact(sock, length)
    return json.loads(body.decode("utf-8"))


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed before all bytes received")
        buf += chunk
    return buf


# ---------------------------------------------------------------------------
# TCP Auth request handler  (runs in its own thread per connection)
# ---------------------------------------------------------------------------

class _AuthHandler(socketserver.BaseRequestHandler):
    """
    Handle a single AUTH connection.

    Expected inbound frame:
        { "type": "AUTH", "password": "...", "fp": "<cert fingerprint or null>" }

    Response:
        { "status": "AUTH_OK" }
        { "status": "AUTH_FAIL", "reason": "..." }
    """

    def handle(self):
        sock: socket.socket = self.request
        sock.settimeout(10.0)
        peer = self.client_address

        try:
            msg = _read_json_from_sock(sock)
        except Exception as exc:
            logger.warning(f"[HandshakeService] Bad frame from {peer}: {exc}")
            return

        if msg.get("type") != "AUTH":
            sock.sendall(_encode_json_legacy({"status": "AUTH_FAIL", "reason": "bad_type"}))
            return

        password = msg.get("password", "")
        fp = (msg.get("fp") or "").lower() or None

        # Check if peer is already rejected
        peer_store = PeerStore()
        if fp:
            rec = peer_store.get_peer(fp)
            if rec and rec.get("status") == "rejected":
                sock.sendall(_encode_json_legacy({"status": "AUTH_FAIL", "reason": "rejected_peer"}))
                logger.info(f"[HandshakeService] Rejected peer {fp[:8]}...")
                return

        # Read password from keyring — safe here because we're in a thread
        from config_manager import get_password as _get_pw
        expected = _get_pw() or os.environ.get("PASSWORD")

        if not expected:
            logger.warning("[HandshakeService] No password configured on this receiver")
            sock.sendall(_encode_json_legacy({"status": "AUTH_FAIL", "reason": "no_password_set"}))
            return

        import hmac
        if hmac.compare_digest(password.encode(), expected.encode()):
            if fp:
                # Ensure the peer record exists before approving.
                # On first-time auth no cert was stored, so add a stub entry.
                if peer_store.get_peer(fp) is None:
                    peer_store._data[fp] = {
                        "fingerprint": fp,
                        "cert_pem": None,
                        "status": "pending",
                        "added_at": int(__import__("time").time()),
                        "password_hash": None,
                        "note": "Auto-added via TCP auth",
                    }
                    peer_store._save()
                peer_store.approve_peer(fp)
                logger.info(f"[HandshakeService] {fp[:8]}... → TRUSTED (TCP auth)")
            else:
                logger.info("[HandshakeService] Peer authenticated (no fingerprint)")
            sock.sendall(_encode_json_legacy({"status": "AUTH_OK"}))
        else:
            logger.warning(f"[HandshakeService] Wrong password from {peer}")
            sock.sendall(_encode_json_legacy({"status": "AUTH_FAIL", "reason": "invalid_password"}))


# ---------------------------------------------------------------------------
# Threaded TCP server wrapper
# ---------------------------------------------------------------------------

class HandshakeService:
    """
    Threaded TCP server on port 4437 for password authentication.

    Runs completely independently of the asyncio event loop — no D-Bus
    blocking or event-loop stalls possible.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = AppConfig.HANDSHAKE_PORT):
        self.host = host
        self.port = port
        self._server: Optional[socketserver.TCPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the TCP auth server in a daemon thread."""
        socketserver.TCPServer.allow_reuse_address = True
        self._server = socketserver.ThreadingTCPServer(
            (self.host, self.port), _AuthHandler
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="HandshakeService",
        )
        self._thread.start()
        logger.info(
            f"[HandshakeService] TCP auth server listening on {self.host}:{self.port}"
        )
        print(f"[handshake] TCP auth server listening on {self.host}:{self.port}")

    def stop(self) -> None:
        """Shutdown the server gracefully."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        logger.info("[HandshakeService] Stopped")


# ---------------------------------------------------------------------------
# Convenience coroutine — keeps the existing call-site in receive.py working
# ---------------------------------------------------------------------------

async def start_handshake_service(
    host: str,
    cert_path: str,
    ca_cert_path: str,
    port: int = AppConfig.HANDSHAKE_PORT,
) -> HandshakeService:
    """
    Start the TCP HandshakeService and return it.
    `cert_path` and `ca_cert_path` are accepted for API compatibility but
    not used — auth is password-only over TCP.
    """
    svc = HandshakeService(host=host, port=port)
    svc.start()
    return svc


# ---------------------------------------------------------------------------
# Sender side — authenticate via TCP:4437
# ---------------------------------------------------------------------------

async def tcp_handshake(
    dest_host: str,
    password: str,
    client_cert: Optional[str] = None,
    client_key: Optional[str] = None,
    ca_cert: Optional[str] = None,
) -> bool:
    """
    Authenticate with a remote peer via a plain TCP connection to port 4437.

    Protocol
    --------
    1. Sender opens a TCP socket to dest_host:4437.
    2. Sender sends:  { "type": "AUTH", "password": "...", "fp": "<cert fingerprint or null>" }
    3. Receiver (HandshakeService / _AuthHandler) verifies in its own thread
       (blocking keyring / D-Bus calls are safe here).
    4. Receiver replies: { "status": "AUTH_OK" }  or  { "status": "AUTH_FAIL", "reason": "..." }
    5. Socket is closed.

    No QUIC, no UDP, no asyncio streams.  TCP only.

    Returns True on AUTH_OK, False on any failure.
    """
    port = AppConfig.HANDSHAKE_PORT  # 4437

    # Derive cert fingerprint to send along (best-effort)
    fp: Optional[str] = None
    if client_cert and os.path.isfile(client_cert):
        try:
            fp = fingerprint_pem(open(client_cert).read()).lower()
        except Exception:
            pass

    logger.info(f"[tcp_handshake] Authenticating via TCP:{port} → {dest_host}...")
    print(f"[tcp_handshake] Connecting to {dest_host}:{port} (TCP HandshakeService)...")

    # TCP connect runs in a thread so we don't block the asyncio loop
    try:
        sock = await asyncio.wait_for(
            asyncio.to_thread(_tcp_connect, dest_host, port),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        logger.error(f"[tcp_handshake] Timeout connecting to {dest_host}:{port}")
        return False
    except Exception as exc:
        logger.error(f"[tcp_handshake] TCP connection failed: {exc}")
        return False

    try:
        # Send AUTH frame (legacy format: magic b'P=' + uint16 len + JSON)
        sock.sendall(_encode_json_legacy({"type": "AUTH", "password": password, "fp": fp}))
        print("[tcp_handshake] Sent AUTH request, waiting for response...")

        # Read the response in a thread too (blocking recv)
        response = await asyncio.wait_for(
            asyncio.to_thread(_read_json_from_sock, sock),
            timeout=15.0,
        )
        print(f"[tcp_handshake] Received response: {response}")

        if response.get("status") == "AUTH_OK":
            logger.info(f"[tcp_handshake] ✓ AUTH_OK from {dest_host} — peer trusted")
            return True
        else:
            reason = response.get("reason", "unknown")
            logger.warning(f"[tcp_handshake] AUTH_FAIL from {dest_host}: {reason}")
            return False

    except asyncio.TimeoutError:
        logger.error("[tcp_handshake] Timeout waiting for AUTH response")
        return False
    except Exception as exc:
        logger.error(f"[tcp_handshake] AUTH error: {exc}")
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Backward-compat alias  (old call-sites used the misleading name)
# ---------------------------------------------------------------------------

quic_handshake = tcp_handshake


def _tcp_connect(host: str, port: int) -> socket.socket:
    """Blocking TCP connect — intended to be run in an executor."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10.0)
    sock.connect((host, port))
    return sock


# ---------------------------------------------------------------------------
# initiate_handshake — backward-compat alias
# ---------------------------------------------------------------------------

async def initiate_handshake(
    dest_host: str,
    password: str,
    client_cert_path: str,
    ca_cert_path: str,
) -> bool:
    """Backward-compat alias for tcp_handshake()."""
    return await tcp_handshake(
        dest_host=dest_host,
        password=password,
        client_cert=client_cert_path,
        ca_cert=ca_cert_path,
    )
