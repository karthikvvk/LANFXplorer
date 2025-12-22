#!/usr/bin/env python3
import asyncio
import os
import sys

from startsetup import load_env_vars
from sender_api_functions import quic_connect, send_file, close_connection


async def interactive_loop(connection, default_src_dir: str | None = None) -> None:

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


        if default_src_dir and not os.path.isabs(raw):
            file_path = os.path.join(default_src_dir, raw)
        else:
            file_path = raw

        if not os.path.isfile(file_path):
            print(f"[sender] Not a file: {file_path}")
            continue

        await send_file(connection, file_path)


async def main() -> None:

    env = load_env_vars()
    dest_host = env.get("dest_host") or env.get("recivhost") or "127.0.0.1"
    port = env.get("port")
    if isinstance(port, str):
        port = int(port)
    if not port:
        port = 4433
        
    src_dir = env.get("src_dir") or ""  
    ca_cert = env.get("ca_cert")
    client_cert = env.get("certi")
    client_key = env.get("key")

    if not dest_host or dest_host == "0.0.0.0":
        print("[sender] ERROR: DEST_HOST must be set in .env (or RECIVHOST cannot be 0.0.0.0)")
        sys.exit(1)

    if not ca_cert:
        print("[sender] ERROR: CA_CERT must be set in .env for secure connections")
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
    print(f"          CA_CERT={ca_cert}")



    connection = await quic_connect(
        host=dest_host,
        port=port,
        insecure=False, 
        client_cert=client_cert,
        client_key=client_key,
        ca_cert=ca_cert,
        server_name=None,  
    )

    print(f"[sender] Connected to {dest_host}:{port}")

    try:
        await interactive_loop(connection, default_src_dir=src_dir)
    finally:
        await close_connection(connection)
        print("[sender] Connection closed (program exiting).")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[sender] KeyboardInterrupt, exiting.")
