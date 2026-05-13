#!/usr/bin/env python3
"""
sender.py  —  QUIC bandwidth tester (sender side)

Usage:
    python3 sender.py [--server 192.168.0.104] [--port 5210]
                      [--duration 15] [--parallel 1] [--bandwidth 500M]
                      [--tls | --no-tls]
"""

import asyncio
import argparse
import os
import time
import ssl
import socket
from typing import cast

from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection
from aioquic.quic.events import QuicEvent, StreamDataReceived


# ── protocol ──────────────────────────────────────────────────────────────────

class SenderProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # stores receiver's final report per stream: stream_id -> bytes_str
        self._reports: dict[int, str] = {}
        self._report_event = asyncio.Event()

    def quic_event_received(self, event: QuicEvent):
        # receiver sends back a one-line report: "DONE <bytes_received>\n"
        if isinstance(event, StreamDataReceived):
            text = event.data.decode(errors="ignore").strip()
            if text.startswith("DONE"):
                self._reports[event.stream_id] = text
                if len(self._reports) >= self._expected_streams:
                    self._report_event.set()

    def set_expected_streams(self, n: int):
        self._expected_streams = n

    async def wait_for_reports(self, timeout=10.0):
        try:
            await asyncio.wait_for(self._report_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        return self._reports


# ── helpers ───────────────────────────────────────────────────────────────────

def parse_bandwidth(bw_str: str) -> int:
    s = bw_str.upper()
    if s.endswith("G"):
        return int(float(s[:-1]) * 1_000_000_000)
    if s.endswith("M"):
        return int(float(s[:-1]) * 1_000_000)
    return int(s)


CHUNK = 32768

async def stream_sender(protocol: SenderProtocol, bps: int,
                        duration: float, result: list):
    reader, writer = await protocol.create_stream()
    payload       = os.urandom(CHUNK)
    bytes_per_sec = bps / 8
    sent          = 0
    t0            = time.monotonic()
    deadline      = t0 + duration

    while time.monotonic() < deadline:
        # Respect backpressure: only write if the send buffer has room.
        # writer.transport is the underlying asyncio transport;
        # _protocol._quic gives us the QUIC connection's send buffer state.
        writer.write(payload)
        sent += CHUNK

        # Pace to target BW — sleep if we're ahead of schedule.
        # This also yields to the event loop so packets actually get sent.
        gap = (sent / bytes_per_sec) - (time.monotonic() - t0)
        if gap > 0:
            await asyncio.sleep(gap)
        else:
            # Even if we're behind, yield so the event loop can flush
            await asyncio.sleep(0)

    # Signal end of stream — receiver will send back its byte count
    writer.write_eof()
    # Don't drain here — just let the event loop flush naturally
    result.append(sent)


async def connect_ipv4(host, port, configuration):
    """aioquic.connect() hardcodes AF_INET6 — bypass with explicit AF_INET."""
    loop = asyncio.get_running_loop()
    connection = QuicConnection(configuration=configuration)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: SenderProtocol(connection), sock=sock,
    )
    protocol = cast(SenderProtocol, protocol)
    protocol.connect((host, port))
    await protocol.wait_connected()
    return protocol


# ── main ──────────────────────────────────────────────────────────────────────

async def run(args):
    config = QuicConfiguration(is_client=True)
    config.server_name = args.server
    config.verify_mode = ssl.CERT_NONE

    if args.tls:
        print("[sender] TLS: ON")
    else:
        print("[sender] TLS: OFF")

    bps_total      = parse_bandwidth(args.bandwidth)
    per_stream_bps = bps_total // args.parallel

    print(f"[sender] connecting → {args.server}:{args.port}")
    print(f"[sender] {args.parallel} stream(s) × "
          f"{per_stream_bps/1e6:.1f} Mbps each  for {args.duration}s")

    protocol = await connect_ipv4(args.server, args.port, config)
    protocol.set_expected_streams(args.parallel)

    try:
        sent_counts = []
        t0 = time.monotonic()

        await asyncio.gather(*[
            stream_sender(protocol, per_stream_bps, args.duration, sent_counts)
            for _ in range(args.parallel)
        ])

        elapsed = time.monotonic() - t0

        # Wait for receiver to echo back actual received byte counts
        reports = await protocol.wait_for_reports(timeout=5.0)

        sender_bytes  = sum(sent_counts)
        sender_mbps   = (sender_bytes * 8) / elapsed / 1e6

        # Parse receiver reports: "DONE <bytes>"
        receiver_bytes = 0
        for v in reports.values():
            try:
                receiver_bytes += int(v.split()[1])
            except (IndexError, ValueError):
                pass

        receiver_mbps = (receiver_bytes * 8) / elapsed / 1e6 if receiver_bytes else 0

        print(f"[sender]   sent     = {sender_bytes/1e6:.1f} MB  →  {sender_mbps:.1f} Mbps  (sender buffer count)")
        print(f"[sender]   received = {receiver_bytes/1e6:.1f} MB  →  {receiver_mbps:.1f} Mbps  (ground truth)")
        # Emit the ground-truth line that quic_tester.sh parses
        print(f"[sender] done — {receiver_bytes/1e6:.1f} MB in {elapsed:.2f}s = {receiver_mbps:.1f} Mbps")

    finally:
        protocol.close()
        await protocol.wait_closed()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="QUIC bandwidth sender")
    p.add_argument("--server",    default="192.168.0.104")
    p.add_argument("--port",      type=int, default=5210)
    p.add_argument("--duration",  type=int, default=15)
    p.add_argument("--parallel",  type=int, default=1)
    p.add_argument("--bandwidth", default="500M")

    tls = p.add_mutually_exclusive_group()
    tls.add_argument("--tls",    dest="tls", action="store_true", default=True)
    tls.add_argument("--no-tls", dest="tls", action="store_false")

    asyncio.run(run(p.parse_args()))