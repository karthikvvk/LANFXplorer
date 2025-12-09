#!/usr/bin/env python3
"""
Sender-side QUIC API functions using aioquic.

This module provides a function-based API so you can reuse a single
QUIC connection and open multiple streams to send files or raw bytes.

Protocol per stream:
    [2 bytes] filename length (big-endian unsigned short)
    [N bytes] filename (UTF-8)
    [8 bytes] file size in bytes (big-endian unsigned long long)
    [..]      file data
"""

import os
import ssl
import struct
from dataclasses import dataclass
from typing import Optional

from aioquic.asyncio import connect as _quic_connect
from aioquic.quic.configuration import QuicConfiguration


# -----------------------------
# Small helper wrapper for the connection
# -----------------------------

@dataclass
class QuicSenderConnection:
    """
    Wrapper representing a persistent QUIC client connection.

    - `protocol` is the aioquic protocol object you can use to create streams.
    - `_cm` is the underlying async context manager used internally.
    """
    protocol: any
    _cm: any

    async def close(self) -> None:
        """
        Gracefully close the underlying QUIC connection and transport.
        """
        # This triggers the same behavior as exiting `async with connect(...)`
        await self._cm.__aexit__(None, None, None)


# -----------------------------
# Internal helpers
# -----------------------------

def _build_header(filename: str, filesize: int) -> bytes:
    """
    Build the metadata header for a stream.

    Header layout:
        [2 bytes] filename length (unsigned short, big-endian)
        [N bytes] filename UTF-8
        [8 bytes] file size (unsigned long long, big-endian)
    """
    filename_bytes = filename.encode("utf-8")
    if len(filename_bytes) > 0xFFFF:
        raise ValueError("Filename too long to encode in header")

    header = struct.pack("!H", len(filename_bytes)) + filename_bytes
    header += struct.pack("!Q", filesize)
    return header


# -----------------------------
# Public API
# -----------------------------

async def quic_connect(
    host: str,
    port: int = 4433,
    *,
    insecure: bool = False,
    server_name: Optional[str] = None,
    alpn_protocol: str = "file-transfer",
) -> QuicSenderConnection:
    """
    Establish a persistent QUIC connection to a receiver and return a
    QuicSenderConnection object.

    Usage:

        conn = await quic_connect("192.168.0.100", 4433, insecure=True)
        await send_file(conn, "/path/to/file.png")
        await conn.close()

    :param host: Receiver hostname or IP.
    :param port: Receiver UDP port.
    :param insecure: If True, disable TLS certificate verification
                     (use only in testing).
    :param server_name: SNI / TLS server name; defaults to `host` if None.
    :param alpn_protocol: ALPN protocol string used by QUIC.
    """
    config = QuicConfiguration(
        is_client=True,
        alpn_protocols=[alpn_protocol],
        server_name=server_name or host,
    )

    if insecure:
        config.verify_mode = ssl.CERT_NONE

    # `_quic_connect` returns an async context manager, which we manage manually.
    cm = _quic_connect(
        host=host,
        port=port,
        configuration=config,
        wait_connected=True,
    )

    protocol = await cm.__aenter__()
    return QuicSenderConnection(protocol=protocol, _cm=cm)


async def send_file(
    connection: QuicSenderConnection,
    file_path: str,
) -> None:
    """
    Send a file over a new QUIC bidirectional stream on an existing connection.

    - Keeps the QUIC connection open.
    - Encodes the filename (optionally with relative directory) in the stream
      header so the receiver can save it with that path under its save_dir.
    """
    abs_path = os.path.abspath(file_path)

    if not os.path.isfile(abs_path):
        # optional: raise or just return
        # raise FileNotFoundError(abs_path)
        return

    # -------- NEW PART: decide what goes into the header --------
    # Try to send a path relative to the sender's CWD.
    # If that doesn't make sense (outside tree), fall back to basename.
    try:
        cwd = os.getcwd()
        rel_path = os.path.relpath(abs_path, cwd)
    except Exception:
        rel_path = os.path.basename(abs_path)

    # If rel_path escapes upwards ("../"), just use basename
    if rel_path.startswith(".."):
        header_name = os.path.basename(abs_path)
    else:
        header_name = rel_path

    # Normalize for cross-platform
    header_name = header_name.replace("\\", "/")
    # ------------------------------------------------------------

    filesize = os.path.getsize(abs_path)
    header = _build_header(header_name, filesize)

    reader, writer = await connection.protocol.create_stream()

    # Write header first
    writer.write(header)

    # Then write file contents
    with open(abs_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            writer.write(chunk)

    await writer.drain()
    writer.write_eof()

    # Optional: read ACK (if receiver sends "OK")
    try:
        ack = await reader.read(1024)
        # handle/log ack if you want
    except Exception:
        pass



async def send_bytes(
    connection: QuicSenderConnection,
    data: bytes,
    filename_hint: str = "data.bin",
) -> None:
    """
    Send raw in-memory bytes as a "virtual file" over a new QUIC stream.

    :param connection: QuicSenderConnection returned by `quic_connect`.
    :param data: Bytes to send.
    :param filename_hint: Suggested filename for receiver to use.
    """
    filename = filename_hint
    filesize = len(data)
    header = _build_header(filename, filesize)

    reader, writer = await connection.protocol.create_stream()

    writer.write(header)
    writer.write(data)

    await writer.drain()
    writer.write_eof()

    try:
        ack = await reader.read(1024)
        # Optional ACK use
    except Exception:
        pass


async def close_connection(connection: QuicSenderConnection) -> None:
    """
    Convenience wrapper to close a QuicSenderConnection.

    Same as calling `await connection.close()`.
    """
    await connection.close()
