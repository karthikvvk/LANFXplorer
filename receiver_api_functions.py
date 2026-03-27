"""
LANFXplorer – QUIC Receiver API (Method 3: Control Stream + Data Stream)

Each inbound transfer uses two QUIC streams:

  STREAM ctrl  ←  4-byte big-endian JSON length + JSON control message
               →  4-byte big-endian JSON length + JSON ack

  STREAM data  ←  raw file bytes + EOF
               →  4-byte big-endian JSON length + JSON final ack  (on ctrl)

The receiver's stream_handler is called for every new stream.  When a
control-type stream arrives (type == FILE or AUTH) we handle it here.
When a data stream arrives (its QUIC stream-id matches a pending entry)
we drain bytes to disk.

Stream-ID correlation:
  The sender embeds "data_stream_id" in the control JSON.
  We keep a per-QuicConnection pending dict:
      {data_stream_id: PendingTransfer}
  The dict lives in a module-level WeakValueDictionary keyed on the
  protocol object so it is automatically GC'd when connections close.
"""

import asyncio
import json
import os
import ssl
import struct
import inspect
import sys
import time
import weakref
from typing import Awaitable, Callable, Optional
from pathlib import Path

APP_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(APP_DIR))

from aioquic.asyncio import serve
from aioquic.quic.configuration import QuicConfiguration

from pki.store import PeerStore
from pki.utils import fingerprint_pem, verify_cert_validity, get_peer_cert_pem_from_writer
from path_security import validate_path_access, get_lanfxplorer_root
from wifi_speed import calculate_optimal_chunk_size
from config_manager import get_password as _get_keyring_password


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

OnFileReceivedCallback = Callable[[str, int], object]


class PendingTransfer:
    """State kept between the control-stream handler and the data-stream handler."""
    __slots__ = (
        "filename", "filesize", "base_dir", "path",
        "ctrl_writer", "on_file_received",
        "chunk_size",
    )

    def __init__(self, filename, filesize, base_dir, path,
                 ctrl_writer, on_file_received, chunk_size):
        self.filename = filename
        self.filesize = filesize
        self.base_dir = base_dir
        self.path = path
        self.ctrl_writer = ctrl_writer
        self.on_file_received = on_file_received
        self.chunk_size = chunk_size


# Per-connection registry: weakref(protocol) → {data_stream_id: PendingTransfer}
# Using a plain dict protected by asyncio (single-threaded event loop).
_pending: "weakref.WeakKeyDictionary[any, dict[int, PendingTransfer]]" = weakref.WeakKeyDictionary()


def _get_pending(protocol) -> dict:
    if protocol not in _pending:
        _pending[protocol] = {}
    return _pending[protocol]


# ---------------------------------------------------------------------------
# Wire-format helpers
# ---------------------------------------------------------------------------

def _encode_json(obj: dict) -> bytes:
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    return struct.pack("!I", len(body)) + body


async def _write_json(writer, obj: dict) -> None:
    writer.write(_encode_json(obj))
    await writer.drain()


async def _read_json(reader) -> dict:
    raw_len = await reader.readexactly(4)
    (length,) = struct.unpack("!I", raw_len)
    if length > 10 * 1024 * 1024:
        raise ValueError(f"Control frame too large: {length} bytes")
    body = await reader.readexactly(length)
    return json.loads(body.decode("utf-8"))


# ---------------------------------------------------------------------------
# Callback helper
# ---------------------------------------------------------------------------

async def _call_callback(
    callback: Optional[OnFileReceivedCallback],
    filepath: str,
    filesize: int,
) -> None:
    if callback is None:
        return
    if inspect.iscoroutinefunction(callback):
        await callback(filepath, filesize)
    else:
        await asyncio.to_thread(callback, filepath, filesize)


# ---------------------------------------------------------------------------
# Main stream handler  (called for every new inbound QUIC stream)
# ---------------------------------------------------------------------------

async def _handle_stream(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    on_file_received: Optional[OnFileReceivedCallback],
    save_dir: Optional[str] = None,
    require_client_cert: bool = False,
) -> None:
    peer_addr = writer.get_extra_info("peername")
    stream_id = writer.get_extra_info("stream_id")
    # QuicStreamAdapter (aioquic) exposes .protocol on its transport, not via get_extra_info
    try:
        protocol = writer._transport.protocol
    except AttributeError:
        protocol = None

    print(f"[receiver] New stream id={stream_id} from {peer_addr}")

    # ------------------------------------------------------------------
    # Data stream? Look up the pending transfer registered by the ctrl handler.
    # Retry briefly in case the control-stream coroutine hasn't committed
    # the pending entry yet (narrow scheduling race on busy loops).
    # ------------------------------------------------------------------
    if protocol is not None:
        pending_map = _get_pending(protocol)
        if stream_id in pending_map:
            await _handle_data_stream(reader, writer, stream_id, pending_map)
            return
        # Retry up to 500 ms (10 × 50 ms) before treating as control stream
        for _ in range(10):
            await asyncio.sleep(0.05)
            if stream_id in pending_map:
                await _handle_data_stream(reader, writer, stream_id, pending_map)
                return

    # ------------------------------------------------------------------
    # Control stream — read the JSON control message first.
    # ------------------------------------------------------------------
    try:
        # TLS cert extraction (best-effort — aioquic limitation)
        tls_cert_pem = None
        tls_fp = None
        try:
            tls_cert_pem = get_peer_cert_pem_from_writer(writer)
            if tls_cert_pem:
                if not verify_cert_validity(tls_cert_pem):
                    await _write_json(writer, {"status": "REJECTED", "reason": "cert_expired"})
                    return
                tls_fp = fingerprint_pem(tls_cert_pem).lower()
        except Exception:
            pass

        msg = await _read_json(reader)
        msg_type = msg.get("type", "FILE")

        # --------------------------------------------------------------
        # AUTH
        # --------------------------------------------------------------
        if msg_type == "AUTH":
            await _handle_auth(msg, writer, tls_fp, tls_cert_pem)
            return

        # --------------------------------------------------------------
        # FILE  – validate, then register pending data stream
        # --------------------------------------------------------------
        if msg_type == "FILE":
            await _handle_file_ctrl(
                msg, reader, writer, stream_id, protocol,
                tls_fp, tls_cert_pem,
                on_file_received, save_dir, require_client_cert,
            )
            return

        # Unknown type
        await _write_json(writer, {"status": "REJECTED", "reason": "unknown_type"})

    except asyncio.IncompleteReadError as e:
        print(f"[receiver] Incomplete read on stream {stream_id}: {e}")
    except Exception as exc:
        import traceback
        print(f"[receiver] Stream {stream_id} error: {exc}")
        print(traceback.format_exc())
    finally:
        try:
            writer.write_eof()
            await writer.drain()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# AUTH handler
# ---------------------------------------------------------------------------

async def _handle_auth(msg: dict, writer, tls_fp: Optional[str], tls_cert_pem) -> None:
    header_fp = (msg.get("fp") or "").lower() or None
    password   = msg.get("password", "")
    auth_fp    = tls_fp or header_fp

    peer_store = PeerStore()
    if auth_fp and peer_store.get_peer_status(auth_fp) == "rejected":
        await _write_json(writer, {"status": "AUTH_FAIL", "reason": "rejected_peer"})
        return

    # Read password from keyring (same source as handshake service used)
    # Fall back to env var for backward compatibility in test environments
    expected_pass = _get_keyring_password() or os.environ.get("PASSWORD")
    if not expected_pass:
        print("[receiver] AUTH: no password configured in keyring or env")
        await _write_json(writer, {"status": "AUTH_FAIL", "reason": "no_password_set"})
        return

    if password == expected_pass:
        if auth_fp:
            store = PeerStore()
            store.update_peer_status(auth_fp, "trusted")
            print(f"[receiver] Peer {auth_fp[:8]}... authenticated via QUIC AUTH → TRUSTED")
        else:
            print("[receiver] Peer authenticated via QUIC AUTH (no cert fingerprint)")
        await _write_json(writer, {"status": "AUTH_OK"})
    else:
        print(f"[receiver] QUIC AUTH FAILED for {tls_fp or 'unknown'}")
        await _write_json(writer, {"status": "AUTH_FAIL", "reason": "invalid_password"})


# ---------------------------------------------------------------------------
# FILE control-stream handler
# ---------------------------------------------------------------------------

async def _handle_file_ctrl(
    msg: dict,
    reader,
    writer,
    stream_id: int,
    protocol,
    tls_fp: Optional[str],
    tls_cert_pem,
    on_file_received,
    save_dir,
    require_client_cert: bool,
) -> None:
    header_fp       = (msg.get("fp") or "").lower() or None
    filename_raw    = msg.get("filename", "")
    filesize        = int(msg.get("filesize", 0))
    dest_dir_raw    = msg.get("dest_dir") or None
    data_stream_id  = msg.get("data_stream_id")

    # Fingerprint consistency
    if require_client_cert and not tls_fp:
        await _write_json(writer, {"status": "REJECTED", "reason": "no_client_cert"})
        return

    if tls_fp and header_fp and tls_fp != header_fp:
        await _write_json(writer, {"status": "REJECTED", "reason": "fingerprint_mismatch"})
        return

    peer_fingerprint = tls_fp or header_fp

    # Peer trust check
    store = PeerStore()
    if peer_fingerprint:
        if store.is_revoked(peer_fingerprint):
            await _write_json(writer, {"status": "REJECTED", "reason": "revoked"})
            return
        rec = store.get_peer(peer_fingerprint)
        if rec is None:
            if tls_cert_pem:
                store.add_pending(cert_pem=tls_cert_pem, note="Auto-discovered via TLS")
            await _write_json(writer, {"status": "REJECTED", "reason": "pending"})
            return
        if rec.get("status") != "trusted":
            await _write_json(writer, {"status": "REJECTED", "reason": "not_trusted"})
            return
    elif require_client_cert:
        await _write_json(writer, {"status": "REJECTED", "reason": "cert_extraction_failed"})
        return

    # Sanitise filename
    filename = filename_raw.lstrip("/")
    parts = filename.replace("\\", "/").split("/")
    safe_parts = [p for p in parts if p and p != ".."]
    filename = "/".join(safe_parts) if safe_parts else "unnamed_file"

    # Destination directory
    dest_dir_override = None
    if dest_dir_raw:
        is_valid, error_msg = validate_path_access(dest_dir_raw)
        if not is_valid:
            print(f"[receiver] SECURITY: Rejected dest_dir: {error_msg}")
            await _write_json(writer, {"status": "REJECTED", "reason": "invalid_dest_dir"})
            return
        dest_dir_override = dest_dir_raw.replace("\\", "/").rstrip("/")

    base_dir = dest_dir_override if dest_dir_override else (save_dir or get_lanfxplorer_root())
    is_valid, error_msg = validate_path_access(base_dir)
    if not is_valid:
        await _write_json(writer, {"status": "REJECTED", "reason": "invalid_save_dir"})
        return

    if peer_fingerprint and not dest_dir_override:
        base_dir = os.path.join(base_dir, peer_fingerprint)
    os.makedirs(base_dir, exist_ok=True)

    path = os.path.normpath(os.path.abspath(os.path.join(base_dir, filename)))
    is_valid, error_msg = validate_path_access(path)
    if not is_valid:
        await _write_json(writer, {"status": "REJECTED", "reason": "invalid_save_path"})
        return

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    print(f"[receiver] [{time.asctime()}] Accepting FILE '{filename}' ({filesize} bytes) → {path}")

    # Register pending data stream so _handle_stream routes correctly
    chunk_size = calculate_optimal_chunk_size(file_size_bytes=filesize)
    pending = PendingTransfer(
        filename=filename,
        filesize=filesize,
        base_dir=base_dir,
        path=path,
        ctrl_writer=writer,
        on_file_received=on_file_received,
        chunk_size=chunk_size,
    )

    if protocol is not None and data_stream_id is not None:
        _get_pending(protocol)[data_stream_id] = pending

    # ACK the control message
    await _write_json(writer, {"status": "OK"})

    # If no protocol reference we cannot correlate by stream ID;
    # fall back to reading data inline on this same stream (degraded mode).
    if protocol is None or data_stream_id is None:
        print("[receiver] WARNING: no stream-id correlation info; reading data inline.")
        await _drain_data_inline(reader, path, filesize, chunk_size,
                                 on_file_received, writer)


# ---------------------------------------------------------------------------
# Data stream handler  (routed from _handle_stream)
# ---------------------------------------------------------------------------

async def _handle_data_stream(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    stream_id: int,
    pending_map: dict,
) -> None:
    pending: PendingTransfer = pending_map.pop(stream_id)
    path       = pending.path
    chunk_size = pending.chunk_size
    filesize   = pending.filesize
    ctrl_writer = pending.ctrl_writer

    print(f"[receiver] [{time.asctime()}] Data stream {stream_id}: writing to {path}")

    try:
        bytes_written = 0
        with open(path, "wb") as f:
            while True:
                chunk = await reader.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                bytes_written += len(chunk)

        print(f"[receiver] ✓ File saved: {path} ({bytes_written} bytes)")
        await _call_callback(pending.on_file_received, path, bytes_written)

        # Send final ack on the control stream — drain before closing
        try:
            await _write_json(ctrl_writer, {"status": "OK"})
            await ctrl_writer.drain()
        except Exception:
            pass

    except Exception as exc:
        import traceback
        print(f"[receiver] Data stream {stream_id} error: {exc}")
        print(traceback.format_exc())
        try:
            await _write_json(ctrl_writer, {"status": "ERROR", "reason": str(exc)})
            await ctrl_writer.drain()
        except Exception:
            pass
    finally:
        try:
            writer.write_eof()
            await writer.drain()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Inline data fallback (no stream-ID info)
# ---------------------------------------------------------------------------

async def _drain_data_inline(reader, path, filesize, chunk_size,
                              on_file_received, ctrl_writer) -> None:
    """Read remaining bytes on the same stream (degraded / legacy mode)."""
    try:
        bytes_written = 0
        with open(path, "wb") as f:
            while True:
                chunk = await reader.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                bytes_written += len(chunk)
        print(f"[receiver] ✓ File saved (inline): {path} ({bytes_written} bytes)")
        await _call_callback(on_file_received, path, bytes_written)
        await _write_json(ctrl_writer, {"status": "OK"})
    except Exception as exc:
        print(f"[receiver] Inline data error: {exc}")
        try:
            await _write_json(ctrl_writer, {"status": "ERROR", "reason": str(exc)})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

async def start_receiver(
    host: str = "0.0.0.0",
    port: int = 4433,
    *,
    certificate: str,
    private_key: str,
    ca_cert: Optional[str] = None,
    alpn_protocol: str = "file-transfer",
    on_file_received: Optional[OnFileReceivedCallback] = None,
    save_dir: Optional[str] = None,
    require_client_cert: bool = False,
):
    if require_client_cert and not ca_cert:
        raise ValueError("require_client_cert=True but ca_cert is not provided")

    config = QuicConfiguration(is_client=False, alpn_protocols=[alpn_protocol])
    config.load_cert_chain(certificate, private_key)

    if ca_cert:
        config.load_verify_locations(cafile=ca_cert)
        config.verify_mode = ssl.CERT_NONE
    elif require_client_cert:
        raise ValueError("require_client_cert=True but ca_cert not provided")

    def stream_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        asyncio.create_task(
            _handle_stream(reader, writer, on_file_received, save_dir, require_client_cert)
        )

    server = await serve(
        host=host,
        port=port,
        configuration=config,
        stream_handler=stream_handler,
    )
    return server


async def stop_receiver(server) -> None:
    server.close()
    if hasattr(server, "wait_closed"):
        await server.wait_closed()
