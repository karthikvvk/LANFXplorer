# quic_transfer.py
import asyncio
import os
from aioquic.asyncio import connect, serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration

CHUNK_SIZE = 1024 * 128  # 128KB

# =========================
# QUIC SERVER SIDE
# =========================
class FileServerProtocol(QuicConnectionProtocol):
    async def stream_created(self, stream_id):
        reader, writer = self._stream(stream_id)
        meta = (await reader.read(2048)).decode().strip().split("||")

        mode, filename, offset = meta[0], meta[1], int(meta[2])
        print(f"[SERVER] {mode.upper()} request for {filename} (resume offset {offset})")

        if mode == "copy":
            if os.path.exists(filename):
                with open(filename, "rb") as f:
                    f.seek(offset)
                    while True:
                        data = f.read(CHUNK_SIZE)
                        if not data:
                            break
                        writer.write(data)
                        await writer.drain()
            writer.write_eof()

        elif mode == "delete":
            if os.path.exists(filename):
                os.remove(filename)
            writer.write(b"deleted")
            writer.write_eof()

        elif mode == "move":
            if os.path.exists(filename):
                with open(filename, "rb") as f:
                    f.seek(offset)
                    while True:
                        data = f.read(CHUNK_SIZE)
                        if not data:
                            break
                        writer.write(data)
                        await writer.drain()
                os.remove(filename)
            writer.write_eof()

        writer.close()


async def start_quic_server(host="0.0.0.0", port=4443):
    config = QuicConfiguration(is_client=False)
    config.verify_mode = False
    await serve(host, port, configuration=config, create_protocol=FileServerProtocol)
    print(f"[SERVER] QUIC running at {host}:{port}")


# =========================
# QUIC CLIENT SIDE
# =========================
async def quic_transfer_file(host, port, mode, source, destination):
    config = QuicConfiguration(is_client=True)
    config.verify_mode = False
    offset = 0
    if os.path.exists(destination):
        offset = os.path.getsize(destination)

    async with connect(host, port, configuration=config) as client:
        stream_id = client.get_next_available_stream_id()
        reader, writer = client.create_stream(stream_id)

        # send metadata header: mode||filename||offset
        writer.write(f"{mode}||{source}||{offset}".encode())
        await writer.drain()

        if mode == "copy" or mode == "move":
            with open(destination, "ab") as f:
                while True:
                    chunk = await reader.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)

        elif mode == "delete":
            res = await reader.read(1024)
            print("[CLIENT] delete response:", res.decode())

        writer.close()

    return {"status": 0, "output": f"{mode} completed", "error": ""}
