#!/usr/bin/env python3
"""
receiver.py  —  QUIC bandwidth tester (receiver / server side)

Usage:
    python3 receiver.py [--host 0.0.0.0] [--port 5210]
                        [--tls | --no-tls]
                        [--cert cert.pem] [--key key.pem]
"""

import asyncio
import argparse
import time
import socket
import sys

from aioquic.asyncio.server import QuicServer
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, ConnectionTerminated


# ── protocol ──────────────────────────────────────────────────────────────────

class ReceiverProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # per stream: bytes received and whether the stream is done
        self._stream_bytes: dict[int, int]  = {}
        self._stream_done:  dict[int, bool] = {}
        self._t_start = time.monotonic()

    def quic_event_received(self, event):
        if isinstance(event, StreamDataReceived):
            sid = event.stream_id
            self._stream_bytes[sid] = (
                self._stream_bytes.get(sid, 0) + len(event.data)
            )
            if event.end_stream:
                self._stream_done[sid] = True
                self._on_stream_done(sid)

        elif isinstance(event, ConnectionTerminated):
            elapsed = time.monotonic() - self._t_start
            total   = sum(self._stream_bytes.values())
            mbps    = (total * 8) / elapsed / 1e6 if elapsed > 0 else 0
            print(
                f"[receiver] connection closed — "
                f"streams={len(self._stream_bytes)}  "
                f"bytes={total/1e6:.2f} MB  "
                f"time={elapsed:.2f}s  "
                f"throughput={mbps:.1f} Mbps  ← GROUND TRUTH"
            )

    def _on_stream_done(self, sid: int):
        """
        When a stream ends, echo the received byte count back to the sender
        on the same stream ID so sender can report accurate numbers.
        """
        received = self._stream_bytes.get(sid, 0)
        report   = f"DONE {received}\n".encode()
        self._quic.send_stream_data(sid, report, end_stream=True)
        self.transmit()


# ── IPv4-safe serve ───────────────────────────────────────────────────────────

async def serve_ipv4(host, port, configuration):
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    server = QuicServer(
        configuration=configuration,
        create_protocol=ReceiverProtocol,
        stream_handler=None,
        session_ticket_fetcher=None,
        session_ticket_handler=None,
        retry=False,
    )
    transport, _ = await loop.create_datagram_endpoint(lambda: server, sock=sock)
    return server, transport, sock


# ── main ──────────────────────────────────────────────────────────────────────

async def run(args):
    config = QuicConfiguration(is_client=False)

    if args.tls:
        if not args.cert or not args.key:
            print("[receiver] ERROR: --tls requires --cert and --key")
            print("  Generate with:")
            print("    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 \\")
            print("      -keyout key.pem -out cert.pem -days 365 -nodes -subj '/CN=localhost'")
            sys.exit(1)
        config.load_cert_chain(args.cert, args.key)
        print(f"[receiver] TLS: ON   cert={args.cert}  key={args.key}")
    else:
        print("[receiver] TLS: OFF")

    print(f"[receiver] listening on {args.host}:{args.port}  (Ctrl-C to stop)")

    server, transport, sock = await serve_ipv4(args.host, args.port, config)

    try:
        await asyncio.Future()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        transport.close()
        sock.close()
        print("[receiver] stopped")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="QUIC bandwidth receiver")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=5210)
    p.add_argument("--cert", default=None)
    p.add_argument("--key",  default=None)

    tls = p.add_mutually_exclusive_group()
    tls.add_argument("--tls",    dest="tls", action="store_true", default=True)
    tls.add_argument("--no-tls", dest="tls", action="store_false")

    asyncio.run(run(p.parse_args()))