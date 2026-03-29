"""
LANFXplorer – QUIC Sender API (Method 3: Control Stream + Data Stream)

Protocol:
  For every file transfer two QUIC streams are used:

    STREAM ctrl  →  4-byte big-endian JSON length + JSON control message
                 ←  4-byte big-endian JSON length + JSON ack

    STREAM data  →  raw file bytes + EOF
                 ←  4-byte big-endian JSON length + JSON final ack

  Control message schema:
    { "type": "FILE",
      "filename": "<safe relative path or basename>",
      "filesize": <int>,
      "fp":       "<cert fingerprint or null>",
      "dest_dir": "<optional remote dest dir or null>",
      "data_stream_id": <int>   -- QUIC stream ID of the paired data stream
    }

  Ack schema:
    { "status": "OK" }
    { "status": "REJECTED", "reason": "..." }

NOTE ON AUTH:
  Password authentication is NOT done over QUIC.  Use tcp_handshake() from
  pki/handshake.py, which connects to the remote HandshakeService on TCP:4437.
  No AUTH messages travel over QUIC streams.
"""

import asyncio
import json
import os
import ssl
import struct
from dataclasses import dataclass
from typing import Optional

from aioquic.asyncio import connect as _quic_connect
from aioquic.quic.configuration import QuicConfiguration
from pki.utils import fingerprint_pem, load_cert_pem
from wifi_speed import calculate_optimal_chunk_size


# ---------------------------------------------------------------------------
# Connection wrapper
# ---------------------------------------------------------------------------

@dataclass
class QuicSenderConnection:
    protocol: any
    _cm: any
    client_cert_pem: Optional[str] = None

    async def close(self) -> None:
        await self._cm.__aexit__(None, None, None)


# ---------------------------------------------------------------------------
# Wire-format helpers  (4-byte big-endian length prefix + JSON body)
# ---------------------------------------------------------------------------

def _encode_json(obj: dict) -> bytes:
    """Encode a dict as a length-prefixed JSON frame."""
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    return struct.pack("!I", len(body)) + body


async def _write_json(writer, obj: dict) -> None:
    """Write a length-prefixed JSON frame to a stream writer."""
    writer.write(_encode_json(obj))
    await writer.drain()


async def _read_json(reader) -> dict:
    """Read a length-prefixed JSON frame from a stream reader."""
    raw_len = await reader.readexactly(4)
    (length,) = struct.unpack("!I", raw_len)
    if length > 10 * 1024 * 1024:  # sanity cap: 10 MB JSON is absurd
        raise ValueError(f"Control frame too large: {length} bytes")
    body = await reader.readexactly(length)
    return json.loads(body.decode("utf-8"))


# ---------------------------------------------------------------------------
# Connection setup
# ---------------------------------------------------------------------------

async def quic_connect(
    host: str,
    port: int = 4433,
    *,
    insecure: bool = False,
    server_name: Optional[str] = None,
    alpn_protocol: str = "file-transfer",
    client_cert: Optional[str] = None,
    client_key: Optional[str] = None,
    ca_cert: Optional[str] = None,
) -> QuicSenderConnection:
    if insecure:
        raise ValueError(
            "insecure=True is not allowed. Server certificate verification is "
            "mandatory. Provide ca_cert to verify the server."
        )

    config = QuicConfiguration(
        is_client=True,
        alpn_protocols=[alpn_protocol],
        server_name=server_name or host,
    )
    # Match the receiver's QUIC parameters for large-file robustness.
    config.idle_timeout = 3600.0               # 1 hour — large files take time
    config.max_data = 128 * 1024 * 1024        # 128 MB connection window
    config.max_stream_data = 128 * 1024 * 1024 # 128 MB per-stream window

    if ca_cert:
        config.load_verify_locations(cafile=ca_cert)
        # CERT_NONE bypasses strict clock checks on offline peers;
        # trust is enforced by the P2P Handshake phase.
        config.verify_mode = ssl.CERT_NONE
    else:
        raise ValueError(
            "CA_CERT environment variable not set. "
            "Cannot verify server certificate."
        )

    client_cert_pem = None
    if client_cert and client_key:
        config.load_cert_chain(client_cert, client_key)
        try:
            client_cert_pem = load_cert_pem(client_cert).decode("utf-8")
        except Exception:
            client_cert_pem = None

    cm = _quic_connect(host=host, port=port, configuration=config, wait_connected=True)
    protocol = await cm.__aenter__()
    return QuicSenderConnection(protocol=protocol, _cm=cm, client_cert_pem=client_cert_pem)


# ---------------------------------------------------------------------------
# Internal helper – derive fingerprint tag from connection
# ---------------------------------------------------------------------------

def _fp_from_conn(conn: QuicSenderConnection) -> Optional[str]:
    if conn.client_cert_pem:
        try:
            return fingerprint_pem(conn.client_cert_pem)
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# send_file (basic, no progress callback)
# ---------------------------------------------------------------------------

async def send_file(connection: QuicSenderConnection, file_path: str) -> None:
    abs_path = os.path.abspath(file_path)
    if not os.path.isfile(abs_path):
        print(f"[sender] Not a file: {abs_path}")
        return

    try:
        rel = os.path.relpath(abs_path, os.getcwd())
    except Exception:
        rel = os.path.basename(abs_path)

    filename = os.path.basename(abs_path) if rel.startswith("..") else rel
    filename = filename.replace("\\", "/")
    filesize = os.path.getsize(abs_path)
    fp = _fp_from_conn(connection)

    # --- Control stream ---
    ctrl_reader, ctrl_writer = await connection.protocol.create_stream()
    ctrl_stream_id = ctrl_writer.get_extra_info("stream_id")

    # data stream ID: next client-initiated bidirectional stream
    data_stream_id = ctrl_stream_id + 4

    await _write_json(ctrl_writer, {
        "type": "FILE",
        "filename": filename,
        "filesize": filesize,
        "fp": fp,
        "dest_dir": None,
        "data_stream_id": data_stream_id,
    })

    ack = await _read_json(ctrl_reader)
    if ack.get("status") != "OK":
        print(f"[sender] Transfer rejected: {ack.get('reason', ack)}")
        ctrl_writer.write_eof()
        return

    # --- Data stream ---
    _, data_writer = await connection.protocol.create_stream()
    chunk_size = calculate_optimal_chunk_size(file_size_bytes=filesize)

    with open(abs_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            data_writer.write(chunk)
            await data_writer.drain()  # drain per-chunk so QUIC flow control is respected

    data_writer.write_eof()
    await asyncio.sleep(0)  # yield so QUIC can flush

    # Final ack: scale timeout with file size.
    # Assume minimum 5 MB/s throughput; add 120 s for disk-write overhead.
    ack_timeout = max(60.0, min(3600.0, filesize / (5 * 1024 * 1024) + 120))
    try:
        final = await asyncio.wait_for(_read_json(ctrl_reader), timeout=ack_timeout)
        if final.get("status") != "OK":
            print(f"[sender] Final ack error: {final}")
        else:
            print(f"[sender] ✓ Transfer confirmed by receiver")
    except asyncio.TimeoutError:
        print(f"[sender] Warning: no final ack within {ack_timeout:.0f}s (file may still have been saved)")
    except Exception as e:
        print(f"[sender] Error reading final ack: {e}")

    ctrl_writer.write_eof()


# ---------------------------------------------------------------------------
# send_file_with_progress
# ---------------------------------------------------------------------------

async def send_file_with_progress(
    connection: QuicSenderConnection,
    file_path: str,
    on_progress: callable = None,
    dest_dir: str = None,
    rel_path: str = None,
) -> None:
    abs_path = os.path.abspath(file_path)
    if not os.path.isfile(abs_path):
        return

    if rel_path:
        filename = rel_path.replace("\\", "/")
    else:
        try:
            computed = os.path.relpath(abs_path, os.getcwd())
        except Exception:
            computed = os.path.basename(abs_path)
        filename = os.path.basename(abs_path) if computed.startswith("..") else computed
        filename = filename.replace("\\", "/")

    filesize = os.path.getsize(abs_path)
    fp = _fp_from_conn(connection)

    # Normalise dest_dir
    if dest_dir:
        dest_dir = dest_dir.replace("\\", "/").rstrip("/")

    # --- Control stream ---
    ctrl_reader, ctrl_writer = await connection.protocol.create_stream()
    ctrl_stream_id = ctrl_writer.get_extra_info("stream_id")
    data_stream_id = ctrl_stream_id + 4

    await _write_json(ctrl_writer, {
        "type": "FILE",
        "filename": filename,
        "filesize": filesize,
        "fp": fp,
        "dest_dir": dest_dir,
        "data_stream_id": data_stream_id,
    })

    ack = await _read_json(ctrl_reader)
    if ack.get("status") != "OK":
        print(f"[sender] Transfer rejected: {ack.get('reason', ack)}")
        ctrl_writer.write_eof()
        return

    # --- Data stream ---
    _, data_writer = await connection.protocol.create_stream()
    chunk_size = calculate_optimal_chunk_size(file_size_bytes=filesize)
    bytes_sent = 0

    with open(abs_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            data_writer.write(chunk)
            await data_writer.drain()
            bytes_sent += len(chunk)
            if on_progress:
                try:
                    on_progress(bytes_sent)
                except Exception:
                    pass

    await data_writer.drain()
    data_writer.write_eof()
    await asyncio.sleep(0)  # yield so QUIC can flush

    # Final ack: scale timeout with file size.
    # Assume minimum 5 MB/s throughput; add 120 s for disk-write overhead.
    ack_timeout = max(60.0, min(3600.0, filesize / (5 * 1024 * 1024) + 120))
    try:
        final = await asyncio.wait_for(_read_json(ctrl_reader), timeout=ack_timeout)
        if final.get("status") != "OK":
            print(f"[sender] Final ack error: {final}")
        else:
            print(f"[sender] ✓ Transfer confirmed by receiver ({bytes_sent} bytes)")
    except asyncio.TimeoutError:
        print(f"[sender] Warning: no final ack within {ack_timeout:.0f}s (file may still have been saved)")
    except Exception as e:
        print(f"[sender] Error reading final ack: {e}")

    ctrl_writer.write_eof()


# ---------------------------------------------------------------------------
# send_bytes  (in-memory payload, no data stream re-read needed)
# ---------------------------------------------------------------------------

async def send_bytes(
    connection: QuicSenderConnection,
    data: bytes,
    filename_hint: str = "data.bin",
) -> None:
    filename = filename_hint
    fp = _fp_from_conn(connection)
    filesize = len(data)

    ctrl_reader, ctrl_writer = await connection.protocol.create_stream()
    ctrl_stream_id = ctrl_writer.get_extra_info("stream_id")
    data_stream_id = ctrl_stream_id + 4

    await _write_json(ctrl_writer, {
        "type": "FILE",
        "filename": filename,
        "filesize": filesize,
        "fp": fp,
        "dest_dir": None,
        "data_stream_id": data_stream_id,
    })

    ack = await _read_json(ctrl_reader)
    if ack.get("status") != "OK":
        ctrl_writer.write_eof()
        return

    _, data_writer = await connection.protocol.create_stream()
    data_writer.write(data)
    await data_writer.drain()
    data_writer.write_eof()

    try:
        await _read_json(ctrl_reader)
    except Exception:
        pass

    ctrl_writer.write_eof()


# ---------------------------------------------------------------------------
# close_connection
# ---------------------------------------------------------------------------

async def close_connection(connection: QuicSenderConnection) -> None:
    await connection.close()
