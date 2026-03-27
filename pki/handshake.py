"""
P2P Handshake — QUIC-native implementation (Method 3 / Stage 3).

The TCP-based HandshakeService (port 4437) has been removed.
Auth now travels over a dedicated QUIC control stream using the
AUTH message type already handled by receiver_api_functions._handle_auth().

Public API
----------
quic_handshake(dest_host, password, client_cert, client_key, ca_cert)
    Open a QUIC connection → send AUTH → return True/False → close.

start_handshake_service(...)  [DEPRECATED no-op]
    Retained for import compatibility. Logs a deprecation warning and
    returns None. Callers (receive.py) have been updated to not use it.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

_pki_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(_pki_dir.parent))

from pki.store import PeerStore
from pki.utils import fingerprint_pem, verify_cert_validity
from app_config import AppConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# QUIC-native handshake  (Stage 3 — Method 3)
# ---------------------------------------------------------------------------

async def quic_handshake(
    dest_host: str,
    password: str,
    client_cert: Optional[str] = None,
    client_key: Optional[str] = None,
    ca_cert: Optional[str] = None,
) -> bool:
    """
    Authenticate with a peer over QUIC (no TCP involved).

    Opens a QUIC connection to dest_host:QUIC_PORT, sends an AUTH control
    message, reads the AUTH_OK / AUTH_FAIL response, then closes the connection.

    On AUTH_OK the peer's fingerprint is marked as trusted in the PeerStore.

    Returns True on success, False on any failure.
    """
    # Import here to avoid circular imports
    from sender_api_functions import quic_connect, send_auth, close_connection

    port = AppConfig.QUIC_PORT

    if not ca_cert:
        logger.error("[quic_handshake] ca_cert is required for QUIC connection")
        return False

    logger.info(f"[quic_handshake] Connecting to {dest_host}:{port} via QUIC...")
    try:
        conn = await asyncio.wait_for(
            quic_connect(
                host=dest_host,
                port=port,
                insecure=False,
                client_cert=client_cert,
                client_key=client_key,
                ca_cert=ca_cert,
                server_name=None,
            ),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        logger.error(f"[quic_handshake] Timeout connecting to {dest_host}:{port}")
        return False
    except Exception as e:
        logger.error(f"[quic_handshake] Connection failed: {e}")
        return False

    try:
        logger.info(f"[quic_handshake] QUIC connected. Sending AUTH...")
        success = await asyncio.wait_for(
            send_auth(conn, password),
            timeout=10.0,
        )
        if success:
            logger.info(f"[quic_handshake] ✓ AUTH_OK from {dest_host} — peer trusted")
        else:
            logger.warning(f"[quic_handshake] AUTH_FAIL from {dest_host}")
        return success
    except asyncio.TimeoutError:
        logger.error(f"[quic_handshake] Timeout waiting for AUTH response")
        return False
    except Exception as e:
        logger.error(f"[quic_handshake] AUTH error: {e}")
        return False
    finally:
        try:
            await close_connection(conn)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Deprecated TCP stubs — kept for import compatibility only
# ---------------------------------------------------------------------------

class HandshakeService:
    """
    DEPRECATED — TCP HandshakeService removed in Method 3 migration.
    Auth now runs over QUIC streams. This class is a no-op stub.
    """

    def __init__(self, *args, **kwargs):
        import warnings
        warnings.warn(
            "HandshakeService (TCP:4437) is deprecated. "
            "Auth is now handled over QUIC streams via quic_handshake().",
            DeprecationWarning,
            stacklevel=2,
        )

    async def start(self):
        logger.warning("[HandshakeService] DEPRECATED — no TCP service started")

    async def stop(self):
        pass


async def start_handshake_service(
    host: str,
    cert_path: str,
    ca_cert_path: str,
) -> None:
    """
    DEPRECATED no-op. Previously started TCP HandshakeService on port 4437.
    Auth is now handled natively inside QUIC streams.
    Returns None so callers that do `if handshake_service:` work correctly.
    """
    import warnings
    warnings.warn(
        "start_handshake_service() is deprecated (TCP:4437 removed). "
        "Auth now runs over QUIC. This call does nothing.",
        DeprecationWarning,
        stacklevel=2,
    )
    logger.info("[handshake] TCP HandshakeService DEPRECATED — skipped (auth is QUIC-native now)")
    return None


async def initiate_handshake(
    dest_host: str,
    password: str,
    client_cert_path: str,
    ca_cert_path: str,
) -> bool:
    """
    DEPRECATED — routes to quic_handshake() for backward compatibility.
    Callers should use quic_handshake() directly.
    """
    import warnings
    warnings.warn(
        "initiate_handshake() is deprecated. Use quic_handshake() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return await quic_handshake(
        dest_host=dest_host,
        password=password,
        client_cert=client_cert_path,
        ca_cert=ca_cert_path,
    )
