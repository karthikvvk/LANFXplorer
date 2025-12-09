#!/usr/bin/env python3
import asyncio
import os
import sys

from startsetup import load_env_vars
from sender_api_functions import quic_connect, send_file, close_connection


async def interactive_loop(connection, default_src_dir: str | None = None) -> None:
    """
    Keep the QUIC connection open and let the user send more files
    on demand, each on a new stream.
    """
    if default_src_dir:
        print(f"[sender] Interactive mode using SRCDIR={default_src_dir}")
        print("[sender] Type a filename relative to SRCDIR or an absolute path.")
    else:
        print("[sender] Interactive mode: type a file path to send, or 'quit' to exit.")

    while True:
        user_input = await asyncio.to_thread(input, "file> ")
        raw = user_input.strip()

        if not raw:
            continue

        if raw.lower() in ("quit", "exit"):
            print("[sender] Quitting interactive mode; connection will be closed.")
            break

        # If SRCDIR is set and the user gave a relative path, resolve it
        if default_src_dir and not os.path.isabs(raw):
            file_path = os.path.join(default_src_dir, raw)
        else:
            file_path = raw

        if not os.path.isfile(file_path):
            print(f"[sender] Not a file: {file_path}")
            continue

        await send_file(connection, file_path)


async def main() -> None:
    # Load env variables from .env via your helper
    env = load_env_vars()

    # DEST_HOST is the remote receiver's IP; fallback to RECIVHOST for local receiver
    dest_host = env.get("dest_host") or env.get("recivhost") or "127.0.0.1"
    port = env.get("port") or 4433
    src_dir = env.get("src") or ""  # optional convenience
    # For now we always connect "insecure" (self-signed cert typical in your tests)
    insecure = False

    if not dest_host or dest_host == "0.0.0.0":
        print("[sender] ERROR: DEST_HOST must be set in .env (or RECIVHOST cannot be 0.0.0.0)")
        sys.exit(1)

    if src_dir:
        src_dir = os.path.abspath(src_dir)
        print(f"[sender] Using SRCDIR={src_dir}")
    else:
        src_dir = None

    print(f"[sender] Loaded from env:")
    print(f"          DEST_HOST={dest_host}")
    print(f"          PORT={port}")
    print(f"          SRCDIR={src_dir or '(none)'}")

    # Establish QUIC connection using the API
    connection = await quic_connect(
        host=dest_host,
        port=port,
        insecure=insecure,
        server_name=None,  # will default to host
    )

    print(f"[sender] Connected to {dest_host}:{port}")

    try:
        # No initial CLI file list anymore; everything is via interactive input.
        await interactive_loop(connection, default_src_dir=src_dir)
    finally:
        await close_connection(connection)
        print("[sender] Connection closed (program exiting).")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[sender] KeyboardInterrupt, exiting.")
