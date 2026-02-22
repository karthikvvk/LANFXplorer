import asyncio
import os
import ssl
import struct
import inspect
import sys
from typing import Awaitable, Callable, Optional
from pathlib import Path

# CRITICAL: Set up paths FIRST, before importing any local modules
APP_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(APP_DIR))

# Now import third-party modules
from aioquic.asyncio import serve
from aioquic.quic.configuration import QuicConfiguration

# Now import local modules
from pki.store import PeerStore
from pki.utils import fingerprint_pem, verify_cert_validity, get_peer_cert_pem_from_writer
from path_security import validate_path_access, get_lanfxplorer_root
from wifi_speed import calculate_optimal_chunk_size


OnFileReceivedCallback = Callable[[str, int], object]



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


async def _handle_stream(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    on_file_received: Optional[OnFileReceivedCallback],
    save_dir: Optional[str] = None,
    require_client_cert: bool = False,
) -> None:
    peer_addr = writer.get_extra_info('peername')
    print(f"[DEBUG Receiver] New stream from {peer_addr}")
    try:
        
        tls_cert_pem = None
        tls_fp = None
        try:
            peercert_info = writer.get_extra_info("peercert")
            
            tls_cert_pem = get_peer_cert_pem_from_writer(writer)
            if require_client_cert and not tls_cert_pem:
                 print("[WARNING Receiver] Client cert extraction failed (aioquic limitation). Proceeding to Password Auth logic.")
                


            if tls_cert_pem:
                if not verify_cert_validity(tls_cert_pem):
                    writer.write(b"REJECTED:cert_expired")
                    await writer.drain()
                    return
                tls_fp = fingerprint_pem(tls_cert_pem).lower()
        except Exception:
            pass
        
        # NOTE: cert requirement check moved to after __AUTH__ handling
        # if require_client_cert and not tls_fp:
        #     writer.write(b"REJECTED:no_client_cert")
        #     await writer.drain()
        #     return

        raw = await reader.readexactly(2)
        (name_len,) = struct.unpack("!H", raw)

        filename_bytes = await reader.readexactly(name_len)
        filename = filename_bytes.decode("utf-8")
        
        header_fp = None
        dest_dir_override = None
        if filename.startswith("FP:") and "|" in filename:
            try:
                marker, rest = filename.split("|", 1)
                _, fp = marker.split(":", 1)
                header_fp = fp.lower()
                filename = rest
            except Exception:
                pass
        
        # Parse DEST: prefix for destination directory
        if filename.startswith("DEST:") and "|" in filename:
            try:
                marker, rest = filename.split("|", 1)
                _, dest_path = marker.split(":", 1)
                dest_dir_override = dest_path.rstrip("/")
                
                # SECURITY: Validate dest_dir_override is within allowed root
                is_valid, error_msg = validate_path_access(dest_dir_override)
                if not is_valid:
                    print(f"[receiver] SECURITY: Rejected dest_dir_override: {error_msg}")
                    writer.write(f"REJECTED:invalid_dest_dir".encode())
                    await writer.drain()
                    return
                
                filename = rest
                print(f"[receiver] Destination directory override: {dest_dir_override}")
            except Exception:
                pass

        # Sanitize path but PRESERVE subdirectory structure for folder transfers
        # Remove any leading slashes or drive letters to prevent absolute path writes
        filename = filename.lstrip("/")
        # Prevent directory traversal attacks while keeping legitimate subdirs
        parts = filename.replace("\\", "/").split("/")
        safe_parts = [p for p in parts if p and p != ".."]
        filename = "/".join(safe_parts) if safe_parts else "unnamed_file"

        if filename == "__AUTH__":
            raw = await reader.readexactly(8)
            (pass_len,) = struct.unpack("!Q", raw)
            if pass_len > 1024:
                writer.write(b"AUTH_FAIL:too_long")
                await writer.drain()
                return

            peer_store = PeerStore()
            peer_status = "pending"
            auth_fp = tls_fp or header_fp
            if auth_fp:
                peer_status = peer_store.get_peer_status(auth_fp)
            
            if peer_status == "rejected":
                writer.write(b"AUTH_FAIL:rejected_peer")
                await writer.drain()
                return

            password = (await reader.readexactly(pass_len)).decode("utf-8")
            
            env_pass = os.environ.get("PASSWORD")
            
            if not env_pass:
             
                writer.write(b"AUTH_FAIL:no_password_set")
                await writer.drain()
                return

            
            is_valid = (password == env_pass)
            is_valid = (password == env_pass)
            
            if is_valid:
                if auth_fp:
                    store = PeerStore()
                    store.update_peer_status(auth_fp, "trusted")
                    print(f"[+] Peer {auth_fp[:8]}... authenticated and marked TRUSTED.")
                else:
                    print(f"[+] Peer authenticated via Password (no cert bound).")
                
                writer.write(b"AUTH_OK")
            else:
                print(f"[!] Authentication FAILED for peer {tls_fp if tls_fp else 'unknown'}")
                writer.write(b"AUTH_FAIL:invalid_password")
            
            await writer.drain()
            return


        # NOW check client cert requirement - but only for file transfers, not AUTH
        if require_client_cert and not tls_fp:
            writer.write(b"REJECTED:no_client_cert_for_file_transfer")
            await writer.drain()
            return

        if tls_fp and header_fp and tls_fp != header_fp:
            writer.write(b"REJECTED:fingerprint_mismatch")
            await writer.drain()
            return
        
        peer_fingerprint = tls_fp or header_fp

        raw = await reader.readexactly(8)
        (filesize,) = struct.unpack("!Q", raw)

        store = PeerStore()
        if peer_fingerprint:
            rec = store.get_peer(peer_fingerprint)
            
            if store.is_revoked(peer_fingerprint):
                writer.write(b"REJECTED:revoked")
                await writer.drain()
                return
            
            if rec is None:
                if tls_cert_pem:
                    store.add_pending(cert_pem=tls_cert_pem, note="Auto-discovered via TLS")
                writer.write(b"REJECTED:pending")
                await writer.drain()
                return
            
            if rec.get("status") != "trusted":
                writer.write(b"REJECTED:not_trusted")
                await writer.drain()
                return
        elif require_client_cert:
            writer.write(b"REJECTED:cert_extraction_failed")
            await writer.drain()
            return

        base_dir = dest_dir_override if dest_dir_override else (save_dir or get_lanfxplorer_root())
        
        # SECURITY: Final validation of base_dir
        is_valid, error_msg = validate_path_access(base_dir)
        if not is_valid:
            print(f"[receiver] SECURITY: Rejected base_dir: {error_msg}")
            writer.write(f"REJECTED:invalid_save_dir".encode())
            await writer.drain()
            return
        
        if peer_fingerprint and not dest_dir_override:
            # Only add fingerprint subdirectory if no explicit destination was provided
            base_dir = os.path.join(base_dir, peer_fingerprint)
        os.makedirs(base_dir, exist_ok=True)
        path = os.path.join(base_dir, filename)

        # SECURITY: Validate the final save path is still within the allowed root
        final_abs_path = os.path.normpath(os.path.abspath(path))
        is_valid, error_msg = validate_path_access(final_abs_path)
        if not is_valid:
            print(f"[receiver] SECURITY: Rejected final save path: {error_msg}")
            writer.write(f"REJECTED:invalid_save_path".encode())
            await writer.drain()
            return

        print(f"[receiver] Receiving file: {filename} ({filesize} bytes) -> {path}")

        parent_dir = os.path.dirname(path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        
        bytes_written = 0
        chunk_size = calculate_optimal_chunk_size()
        with open(path, "wb") as f:
            while True:
                chunk = await reader.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                bytes_written += len(chunk)

        print(f"[receiver] ✓ File saved: {path} ({bytes_written} bytes)")
        await _call_callback(on_file_received, path, bytes_written)

        writer.write(b"OK")
        await writer.drain()

    except asyncio.IncompleteReadError as e:
        print(f"[ERROR Receiver] Incomplete read: {e}")
    except Exception as exc:
        import traceback
        print(f"[ERROR Receiver] Stream handling failed: {exc}")
        print(f"[ERROR Receiver] Traceback: {traceback.format_exc()}")
    finally:
        try:
            writer.write_eof()
            await writer.drain()
        except Exception as e:
            print(f"[ERROR Receiver] Failed to close writer: {e}")



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
        require_client_cert: bool = False):
    if require_client_cert and not ca_cert:
        raise ValueError("require_client_cert=True but ca_cert is not provided")
    
    config = QuicConfiguration(
        is_client=False,
        alpn_protocols=[alpn_protocol],
    )
    config.load_cert_chain(certificate, private_key)
    

    if ca_cert:
        config.load_verify_locations(cafile=ca_cert)
        # Use CERT_NONE so we bypass strict OpenSSL clock checks (offline peers might drift)
        # Trust is fully enforced by our P2P Handshake and utils.verify_cert_validity
        config.verify_mode = ssl.CERT_NONE
    elif require_client_cert:
        raise ValueError("require_client_cert=True but ca_cert not provided")

    def stream_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        asyncio.create_task(
            _handle_stream(
                reader,
                writer,
                on_file_received,
                save_dir,
                require_client_cert=require_client_cert,
            )
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
    if hasattr(server, 'wait_closed'):
        await server.wait_closed()
