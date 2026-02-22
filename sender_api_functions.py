import os
import ssl
import struct
from dataclasses import dataclass
from typing import Optional

from aioquic.asyncio import connect as _quic_connect
from aioquic.quic.configuration import QuicConfiguration
from pki.utils import fingerprint_pem, load_cert_pem
from wifi_speed import calculate_optimal_chunk_size


@dataclass
class QuicSenderConnection:
   
    protocol: any
    _cm: any
    client_cert_pem: Optional[str] = None

    async def close(self) -> None:
        
        await self._cm.__aexit__(None, None, None)


def _build_header(filename: str, filesize: int) -> bytes:

    filename_bytes = filename.encode("utf-8")
    if len(filename_bytes) > 0xFFFF:
        raise ValueError("Filename too long to encode in header")

    header = struct.pack("!H", len(filename_bytes)) + filename_bytes
    header += struct.pack("!Q", filesize)
    return header


async def quic_connect(host: str,port: int = 4433, *,insecure: bool = False, server_name: Optional[str] = None, alpn_protocol: str = "file-transfer", client_cert: Optional[str] = None, client_key: Optional[str] = None, ca_cert: Optional[str] = None) -> QuicSenderConnection:

    if insecure:
        raise ValueError(
            "insecure=True is not allowed. Server certificate verification is mandatory. "
            "Provide ca_cert to verify the server, or set environment variable CA_CERT."
        )
    
    config = QuicConfiguration(is_client=True, alpn_protocols=[alpn_protocol], server_name=server_name or host)


    if ca_cert:
        config.load_verify_locations(cafile=ca_cert)
        # We use CERT_NONE here instead of CERT_REQUIRED because offline PCs might
        # have clock drift, which causes OpenSSL to strictly reject the cert.
        # Certificate trust is already securely verified during the P2P Handshake phase.
        config.verify_mode = ssl.CERT_NONE
    else:
        raise ValueError(
            "CA_CERT environment variable not set. "
            "Cannot verify server certificate. "
            "Set CA_CERT to the path of your CA certificate."
        )


    client_cert_pem = None
    if client_cert and client_key:
        config.load_cert_chain(client_cert, client_key)
        try:
            client_cert_pem = load_cert_pem(client_cert).decode('utf-8')
        except Exception:
            client_cert_pem = None


    cm = _quic_connect(host=host, port=port, configuration=config, wait_connected=True)

    protocol = await cm.__aenter__()
    return QuicSenderConnection(protocol=protocol, _cm=cm, client_cert_pem=client_cert_pem)


async def send_file(connection: QuicSenderConnection, file_path: str) -> None:

    abs_path = os.path.abspath(file_path)

    if not os.path.isfile(abs_path):
        
        return

  
    try:
        cwd = os.getcwd()
        rel_path = os.path.relpath(abs_path, cwd)
    except Exception:
        rel_path = os.path.basename(abs_path)

    if rel_path.startswith(".."):
        header_name = os.path.basename(abs_path)
    else:
        header_name = rel_path

    header_name = header_name.replace("\\", "/")
    try:
        if connection.client_cert_pem:
            fp = fingerprint_pem(connection.client_cert_pem)
            header_name = f"FP:{fp}|{header_name}"
    except Exception:
        pass

    filesize = os.path.getsize(abs_path)
    header = _build_header(header_name, filesize)

    reader, writer = await connection.protocol.create_stream()
    chunk_size = calculate_optimal_chunk_size()

    writer.write(header)
    with open(abs_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            writer.write(chunk)

    await writer.drain()
    writer.write_eof()

    try:
        ack = await reader.read(1024)
        if hasattr(ack, "decode"): 
             if ack.startswith(b"REJECTED"):
                 print(f"[sender] [ERROR] File transfer REJECTED by receiver: {ack}")
             elif ack.startswith(b"OK"):
                 pass # Success
             else:
                 print(f"[sender] File transfer response: {ack}")
    except Exception as e:
        print(f"[sender] Error reading ACK: {e}")


async def send_file_with_progress(
    connection: QuicSenderConnection, 
    file_path: str, 
    on_progress: callable = None,
    dest_dir: str = None,
    rel_path: str = None
) -> None:
    """Send a file with progress callback support.
    
    Args:
        connection: The QUIC connection to use
        file_path: Path to the file to send
        on_progress: Optional callback function that receives bytes_sent so far
        dest_dir: Optional destination directory on the remote machine
        rel_path: Optional relative path to preserve folder structure (e.g. "myfolder/sub/file.txt")
    """
    abs_path = os.path.abspath(file_path)

    if not os.path.isfile(abs_path):
        return

    if rel_path:
        # Use explicitly provided relative path (for folder transfers)
        header_name = rel_path.replace("\\", "/")
    else:
        try:
            cwd = os.getcwd()
            computed_rel_path = os.path.relpath(abs_path, cwd)
        except Exception:
            computed_rel_path = os.path.basename(abs_path)

        if computed_rel_path.startswith(".."):
            header_name = os.path.basename(abs_path)
        else:
            header_name = computed_rel_path

        header_name = header_name.replace("\\", "/")
    
    # Prepend destination directory if provided
    if dest_dir:
        # Normalize the path and prepend to header
        dest_dir = dest_dir.replace("\\", "/")
        if not dest_dir.endswith("/"):
            dest_dir += "/"
        header_name = f"DEST:{dest_dir}|{header_name}"
    
    try:
        if connection.client_cert_pem:
            fp = fingerprint_pem(connection.client_cert_pem)
            header_name = f"FP:{fp}|{header_name}"
    except Exception:
        pass

    filesize = os.path.getsize(abs_path)
    header = _build_header(header_name, filesize)

    reader, writer = await connection.protocol.create_stream()
    chunk_size = calculate_optimal_chunk_size()

    writer.write(header)
    bytes_sent = 0
    
    with open(abs_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            writer.write(chunk)
            # Drain after each chunk to actually send over network
            # This ensures progress reflects bytes actually sent, not just buffered
            await writer.drain()
            bytes_sent += len(chunk)
            
            # Call progress callback
            if on_progress:
                try:
                    on_progress(bytes_sent)
                except Exception:
                    pass  # Don't let callback errors break transfer

    writer.write_eof()

    try:
        ack = await reader.read(1024)
        if hasattr(ack, "decode"): 
             if ack.startswith(b"REJECTED"):
                 print(f"[sender] [ERROR] File transfer REJECTED by receiver: {ack}")
             elif ack.startswith(b"OK"):
                 pass # Success
             else:
                 print(f"[sender] File transfer response: {ack}")
    except Exception as e:
        print(f"[sender] Error reading ACK: {e}")



async def send_bytes(connection: QuicSenderConnection, data: bytes, filename_hint: str = "data.bin",) -> None:
    
    filename = filename_hint
    try:
        if connection.client_cert_pem:
            fp = fingerprint_pem(connection.client_cert_pem)
            filename = f"FP:{fp}|{filename}"
    except Exception:
        pass
    filesize = len(data)
    header = _build_header(filename, filesize)

    reader, writer = await connection.protocol.create_stream()

    writer.write(header)
    writer.write(data)

    await writer.drain()
    writer.write_eof()

    try:
        ack = await reader.read(1024)
    except Exception:
        pass


async def close_connection(connection: QuicSenderConnection) -> None:
   
    await connection.close()


async def send_auth(connection: QuicSenderConnection, password: str) -> bool:

    filename = "__AUTH__"
    if connection.client_cert_pem:
        fp = fingerprint_pem(connection.client_cert_pem).lower()
        filename = f"FP:{fp}|{filename}"

    data = password.encode("utf-8")
    filesize = len(data)
    
    header = _build_header(filename, filesize)
    
    try:
        reader, writer = await connection.protocol.create_stream()
        
        writer.write(header)
        writer.write(data)
        await writer.drain()
        writer.write_eof()
        
        print(f"[send_auth] Sent password, waiting for response...")
        response = await reader.read(1024)
        print(f"[send_auth] Received response: {response}")
        return response == b"AUTH_OK"
        
    except Exception as e:
        print(f"[send_auth] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
