#!/usr/bin/env python3
"""
Receiver-side QUIC API functions using aioquic.

This module exposes a function-based API to start and stop a QUIC
listener. Each incoming stream is interpreted as one "file transfer"
using the same protocol as the sender:

    [2 bytes] filename length (big-endian unsigned short)
    [N bytes] filename (UTF-8)
    [8 bytes] file size (big-endian unsigned long long)
    [..]      file data

The file is saved with the original filename in the current working
directory (or wherever you redirect it to), and an optional callback
is invoked when a file is fully received.
"""

import asyncio
import os
import struct
import inspect
from typing import Awaitable, Callable, Optional

from aioquic.asyncio import serve
from aioquic.quic.configuration import QuicConfiguration


# Type for the callback:
#   def on_file_received(filepath: str, filesize: int) -> None | Awaitable[None]
OnFileReceivedCallback = Callable[[str, int], object]


# -----------------------------
# Internal helpers
# -----------------------------

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
        # Run sync callback in a thread to avoid blocking the event loop
        await asyncio.to_thread(callback, filepath, filesize)


async def _handle_stream(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    on_file_received: Optional[OnFileReceivedCallback],
    save_dir: Optional[str] = None,
) -> None:
    """
    Handle a single incoming QUIC stream:
        - Parse header (filename + size)
        - Save file to disk
        - Invoke callback
        - Send ACK
    """
    try:
        # 1) Read filename length (2 bytes)
        raw = await reader.readexactly(2)
        (name_len,) = struct.unpack("!H", raw)

        # 2) Read filename bytes
        filename_bytes = await reader.readexactly(name_len)
        filename = filename_bytes.decode("utf-8")
        filename = os.path.basename(filename) 
        # 3) Read filesize (8 bytes)
        raw = await reader.readexactly(8)
        (filesize,) = struct.unpack("!Q", raw)

        # Determine output path
        base_dir = save_dir or os.getcwd()
        os.makedirs(base_dir, exist_ok=True)
        path = os.path.join(base_dir, filename)

        parent_dir = os.path.dirname(path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        # 4) Read remaining bytes until EOF and write to file
        bytes_written = 0
        with open(path, "wb") as f:
            while True:
                chunk = await reader.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                bytes_written += len(chunk)

        # Optional check
        # print(f"Expected size: {filesize}, received: {bytes_written}")

        # Invoke callback
        await _call_callback(on_file_received, path, bytes_written)

        # Send ACK
        writer.write(b"OK")
        await writer.drain()

    except asyncio.IncompleteReadError:
        # Stream closed unexpectedly; ignore or log as needed
        pass
    except Exception as exc:
        # Log or handle any unexpected error
        # print(f"[receiver_api] Error in _handle_stream: {exc!r}")
        pass
    finally:
        try:
            # Send ACK
            writer.write(b"OK")
            await writer.drain()

            # proper QUIC bidirectional end, prevents ACK loss
            writer.write_eof()
            await writer.drain()

        except Exception:
            pass


# -----------------------------
# Public API
# -----------------------------

async def start_receiver(
    host: str = "0.0.0.0",
    port: int = 4433,
    *,
    certificate: str,
    private_key: str,
    alpn_protocol: str = "file-transfer",
    on_file_received: Optional[OnFileReceivedCallback] = None,
    save_dir: Optional[str] = None,
):
    """
    Start a QUIC receiver (listener) that accepts incoming streams
    and saves each as a file with the original filename.

    :param host: Local host/IP to bind to.
    :param port: UDP port to listen on.
    :param certificate: Path to TLS certificate (PEM).
    :param private_key: Path to TLS private key (PEM).
    :param alpn_protocol: ALPN string; must match sender's.
    :param on_file_received: Optional callback invoked on each file:
                             def on_file_received(filepath: str, filesize: int) -> None | Awaitable[None]
    :param save_dir: Directory to save incoming files; defaults to cwd.

    :return: The aioquic server object. You can keep it and
             call `await stop_receiver(server)` when needed.
    """
    config = QuicConfiguration(
        is_client=False,
        alpn_protocols=[alpn_protocol],
    )
    config.load_cert_chain(certificate, private_key)

    def stream_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        # Spawn the coroutine to actually handle the stream
        asyncio.create_task(_handle_stream(reader, writer, on_file_received, save_dir))

    server = await serve(
        host=host,
        port=port,
        configuration=config,
        stream_handler=stream_handler,
    )

    return server


async def stop_receiver(server) -> None:
    """
    Stop a previously started QUIC receiver.
    """
    server.close()
    await server.wait_closed()
