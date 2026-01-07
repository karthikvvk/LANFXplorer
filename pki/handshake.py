"""
P2P Handshake Service for Password Authentication and Certificate Exchange.

This module implements the connection handshake protocol (steps 4-6):
1. Sender sends password to receiver
2. Receiver validates password and replies "READY_TO_CONNECT" or "REJECTED"
3. Both peers exchange certificates and verify them
4. Sender confirms "TRUSTED" after verification

Protocol runs on TCP port 4437 (HANDSHAKE_PORT).
"""

import asyncio
import logging
import os
import sys
import socket
from pathlib import Path
from typing import Optional, Tuple

# Add parent directory to path for app_config import
_pki_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(_pki_dir.parent))

from pki.utils import fingerprint_pem, verify_cert_validity
from pki.store import PeerStore
from config_manager import get_password
from app_config import AppConfig

logger = logging.getLogger(__name__)

# Use centralized constant from AppConfig
HANDSHAKE_PORT = AppConfig.HANDSHAKE_PORT
PROTOCOL_VERSION = b"P2P_HANDSHAKE_V1"

# Message types
MSG_PASSWORD = b"PASSWORD"
MSG_READY = b"READY_TO_CONNECT"
MSG_REJECTED = b"REJECTED"
MSG_CLIENT_CERT = b"CLIENT_CERT"
MSG_SERVER_CERT = b"SERVER_CERT"
MSG_TRUSTED = b"TRUSTED"


class HandshakeService:
    """Server-side handshake service running on receiver."""
    
    def __init__(self, host: str, cert_path: str, ca_cert_path: str):
        """
        Initialize handshake service.
        
        :param host: IP address to bind to
        :param cert_path: Path to this peer's certificate
        :param ca_cert_path: Path to CA certificate for verification
        
        Note: Password is retrieved securely from config_manager (keyring)
        """
        self.host = host
        self.cert_path = cert_path
        self.ca_cert_path = ca_cert_path
        self.server = None
        
        # Load certificates into memory
        with open(cert_path, 'rb') as f:
            self.cert_pem = f.read()
        with open(ca_cert_path, 'rb') as f:
            self.ca_cert_pem = f.read()
    
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming handshake request from a sender."""
        peer_addr = writer.get_extra_info('peername')
        logger.info(f"[Handshake] Connection from {peer_addr}")
        
        try:
            # Step 1: Read protocol version
            version = await reader.readexactly(len(PROTOCOL_VERSION))
            if version != PROTOCOL_VERSION:
                logger.warning(f"[Handshake] Invalid protocol version from {peer_addr}")
                writer.close()
                await writer.wait_closed()
                return
            
            # Step 2: Read message type (should be PASSWORD)
            msg_type_len = await reader.readexactly(4)
            msg_type_len = int.from_bytes(msg_type_len, 'big')
            msg_type = await reader.readexactly(msg_type_len)
            
            if msg_type != MSG_PASSWORD:
                logger.warning(f"[Handshake] Expected PASSWORD, got {msg_type}")
                writer.close()
                await writer.wait_closed()
                return
            
            # Step 3: Read password
            password_len = await reader.readexactly(4)
            password_len = int.from_bytes(password_len, 'big')
            
            if password_len > 1024:  # Prevent DoS
                logger.warning(f"[Handshake] Password too long from {peer_addr}")
                writer.close()
                await writer.wait_closed()
                return
            
            password_bytes = await reader.readexactly(password_len)
            password = password_bytes.decode('utf-8')
            
            # Step 4: Validate password (from secure keyring storage)
            expected_password = get_password()
            if not expected_password:
                logger.error(f"[Handshake] PASSWORD not configured in keyring")
                writer.close()
                await writer.wait_closed()
                return
            
            if password != expected_password:
                logger.warning(f"[Handshake] Invalid password from {peer_addr}")
                # Send REJECTED
                writer.write(len(MSG_REJECTED).to_bytes(4, 'big'))
                writer.write(MSG_REJECTED)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return
            
            logger.info(f"[Handshake] Password verified for {peer_addr}")
            
            # Step 5: Send READY_TO_CONNECT
            writer.write(len(MSG_READY).to_bytes(4, 'big'))
            writer.write(MSG_READY)
            await writer.drain()
            
            # Step 6: Read CLIENT_CERT message
            msg_type_len = await reader.readexactly(4)
            msg_type_len = int.from_bytes(msg_type_len, 'big')
            msg_type = await reader.readexactly(msg_type_len)
            
            if msg_type != MSG_CLIENT_CERT:
                logger.warning(f"[Handshake] Expected CLIENT_CERT, got {msg_type}")
                writer.close()
                await writer.wait_closed()
                return
            
            # Read client certificate
            cert_len = await reader.readexactly(4)
            cert_len = int.from_bytes(cert_len, 'big')
            client_cert_pem = await reader.readexactly(cert_len)
            
            # Step 7: Verify client certificate
            if not verify_cert_validity(client_cert_pem):
                logger.warning(f"[Handshake] Client certificate invalid or expired")
                writer.close()
                await writer.wait_closed()
                return
            
            client_fp = fingerprint_pem(client_cert_pem)
            logger.info(f"[Handshake] Client cert fingerprint: {client_fp[:16]}...")
            
            # Step 8: Send our certificate
            writer.write(len(MSG_SERVER_CERT).to_bytes(4, 'big'))
            writer.write(MSG_SERVER_CERT)
            writer.write(len(self.cert_pem).to_bytes(4, 'big'))
            writer.write(self.cert_pem)
            await writer.drain()
            
            # Step 9: Wait for TRUSTED confirmation
            msg_type_len = await reader.readexactly(4)
            msg_type_len = int.from_bytes(msg_type_len, 'big')
            msg_type = await reader.readexactly(msg_type_len)
            
            if msg_type == MSG_TRUSTED:
                logger.info(f"[Handshake] Client confirmed trust. Handshake complete!")
                
                # Update peer store
                store = PeerStore()
                store.add_pending(client_cert_pem, note=f"Handshake from {peer_addr[0]}")
                store.approve_peer(client_fp)
                logger.info(f"[Handshake] Peer {client_fp[:16]}... marked as TRUSTED")
            else:
                logger.warning(f"[Handshake] Expected TRUSTED, got {msg_type}")
            
        except asyncio.IncompleteReadError:
            logger.warning(f"[Handshake] Connection closed unexpectedly by {peer_addr}")
        except Exception as e:
            logger.error(f"[Handshake] Error handling client: {e}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
    
    async def start(self):
        """Start the handshake service."""
        # Use reuse_address/reuse_port to allow restart without 'address already in use' error
        self.server = await asyncio.start_server(
            self.handle_client,
            self.host,
            HANDSHAKE_PORT,
            reuse_address=True,
            reuse_port=True
        )
        logger.info(f"[Handshake] Service started on {self.host}:{HANDSHAKE_PORT}")
    
    async def stop(self):
        """Stop the handshake service."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("[Handshake] Service stopped")


async def initiate_handshake(
    dest_host: str,
    password: str,
    client_cert_path: str,
    ca_cert_path: str
) -> bool:
    """
    Client-side: Initiate handshake with a receiver.
    
    :param dest_host: Receiver IP address
    :param password: Password for authentication
    :param client_cert_path: Path to client certificate
    :param ca_cert_path: Path to CA certificate
    :return: True if handshake successful, False otherwise
    """
    try:
        # Load certificates
        with open(client_cert_path, 'rb') as f:
            client_cert_pem = f.read()
        with open(ca_cert_path, 'rb') as f:
            ca_cert_pem = f.read()
        
        logger.info(f"[Handshake] Initiating connection to {dest_host}:{HANDSHAKE_PORT}")
        
        # Connect to receiver
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(dest_host, HANDSHAKE_PORT),
            timeout=10.0
        )
        
        try:
            # Step 1: Send protocol version
            writer.write(PROTOCOL_VERSION)
            await writer.drain()
            
            # Step 2: Send PASSWORD message
            writer.write(len(MSG_PASSWORD).to_bytes(4, 'big'))
            writer.write(MSG_PASSWORD)
            password_bytes = password.encode('utf-8')
            writer.write(len(password_bytes).to_bytes(4, 'big'))
            writer.write(password_bytes)
            await writer.drain()
            
            logger.info(f"[Handshake] Password sent, waiting for response...")
            
            # Step 3: Read response (READY or REJECTED)
            msg_len = await asyncio.wait_for(reader.readexactly(4), timeout=5.0)
            msg_len = int.from_bytes(msg_len, 'big')
            response = await reader.readexactly(msg_len)
            
            if response == MSG_REJECTED:
                logger.error(f"[Handshake] Authentication REJECTED by {dest_host}")
                return False
            
            if response != MSG_READY:
                logger.error(f"[Handshake] Unexpected response: {response}")
                return False
            
            logger.info(f"[Handshake] Receiver ready, exchanging certificates...")
            
            # Step 4: Send client certificate
            writer.write(len(MSG_CLIENT_CERT).to_bytes(4, 'big'))
            writer.write(MSG_CLIENT_CERT)
            writer.write(len(client_cert_pem).to_bytes(4, 'big'))
            writer.write(client_cert_pem)
            await writer.drain()
            
            # Step 5: Read server certificate
            msg_len = await reader.readexactly(4)
            msg_len = int.from_bytes(msg_len, 'big')
            msg_type = await reader.readexactly(msg_len)
            
            if msg_type != MSG_SERVER_CERT:
                logger.error(f"[Handshake] Expected SERVER_CERT, got {msg_type}")
                return False
            
            cert_len = await reader.readexactly(4)
            cert_len = int.from_bytes(cert_len, 'big')
            server_cert_pem = await reader.readexactly(cert_len)
            
            # Step 6: Verify server certificate
            if not verify_cert_validity(server_cert_pem):
                logger.error(f"[Handshake] Server certificate invalid or expired")
                return False
            
            server_fp = fingerprint_pem(server_cert_pem)
            logger.info(f"[Handshake] Server cert verified: {server_fp[:16]}...")
            
            # Step 7: Send TRUSTED confirmation
            writer.write(len(MSG_TRUSTED).to_bytes(4, 'big'))
            writer.write(MSG_TRUSTED)
            await writer.drain()
            
            logger.info(f"[Handshake] ✓ Handshake with {dest_host} completed successfully!")
            
            # Update peer store
            store = PeerStore()
            store.add_pending(server_cert_pem, note=f"Handshake with {dest_host}")
            store.approve_peer(server_fp)
            
            return True
            
        finally:
            writer.close()
            await writer.wait_closed()
    
    except asyncio.TimeoutError:
        logger.error(f"[Handshake] Timeout connecting to {dest_host}")
        return False
    except ConnectionRefusedError:
        logger.error(f"[Handshake] Connection refused by {dest_host}:{HANDSHAKE_PORT}")
        return False
    except Exception as e:
        logger.error(f"[Handshake] Error: {e}")
        return False


async def start_handshake_service(
    host: str,
    cert_path: str,
    ca_cert_path: str
) -> HandshakeService:
    """
    Convenience function to start handshake service.
    
    Note: Password is retrieved securely from config_manager (keyring)
    
    :return: HandshakeService instance
    """
    service = HandshakeService(host, cert_path, ca_cert_path)
    await service.start()
    return service
