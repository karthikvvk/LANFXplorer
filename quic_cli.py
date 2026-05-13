"""
quic_cli.py — Thin wrapper around c_ver/sender and c_ver/receiver MsQuic binaries.

Replaces the aioquic-based sender_api_functions.py / receiver_api_functions.py
for the QUIC transport layer. All other app services (Flask, PKI, TCP auth,
peer discovery) remain unchanged.

Argument sourcing (all from AppConfig / .env — never hardcoded):
  sender   argv: [abs_file_path, config.dest_host, config.port]
  receiver argv: [config.port,   abs_save_path]

Known limitations vs the old aioquic implementation:
  - No TLS verification: sender uses QUIC_CREDENTIAL_FLAG_NO_CERTIFICATE_VALIDATION
  - No Python-level traceback on QUIC failure: only exit code + stderr are available
  - No in-band progress updates over QUIC: Flask /transfer_status time-estimate handles progress
"""

import os
import shutil
import subprocess
from pathlib import Path

from app_config import get_config, AppConfig

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

APP_DIR      = Path(__file__).parent.resolve()
BINARIES_DIR = APP_DIR / "binaries"
SENDER_BIN   = BINARIES_DIR / "sender"
RECEIVER_BIN = BINARIES_DIR / "receiver"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_binaries() -> None:
    """Fail fast with a clear error if the MsQuic binaries haven't been built."""
    for binary in (SENDER_BIN, RECEIVER_BIN):
        if not binary.exists():
            raise FileNotFoundError(
                f"MsQuic binary not found: {binary}\n"
                f"Build with:  cd c_ver && cmake -B build . && cmake --build build\n"
                f"Then copy outputs:  cp c_ver/build/sender c_ver/build/receiver binaries/"
            )


def _ensure_certs_staged() -> None:
    """
    Copy the app's live PKI certs into APP_DIR as server.key / server.crt.

    receiver.cpp line 206 hardcodes:
        QUIC_CERTIFICATE_FILE certFile{ "server.key", "server.crt" };
    relative to the binary's cwd (APP_DIR). The app's canonical cert paths
    come from AppConfig (sourced from .env CERTI / KEY), so we stage them
    before each receiver launch.

    Config → binary mapping:
      .env KEY   → config.key   → APP_DIR/server.key
      .env CERTI → config.certi → APP_DIR/server.crt
    """
    config = get_config()
    key_src = Path(config.key)    # .env KEY  (e.g. /path/to/key.pem)
    crt_src = Path(config.certi)  # .env CERTI (e.g. /path/to/cert.pem)
    key_dst = APP_DIR / "server.key"
    crt_dst = APP_DIR / "server.crt"

    if not key_src.exists():
        raise FileNotFoundError(
            f"Private key not found: {key_src}\n"
            f"Check .env KEY — current value: {config.key}"
        )
    if not crt_src.exists():
        raise FileNotFoundError(
            f"Certificate not found: {crt_src}\n"
            f"Check .env CERTI — current value: {config.certi}"
        )

    shutil.copy2(str(key_src), str(key_dst))
    shutil.copy2(str(crt_src), str(crt_dst))
    print(f"[quic_cli] Certs staged:  {key_dst}  {crt_dst}")


# ---------------------------------------------------------------------------
# Public API — sender
# ---------------------------------------------------------------------------

def send_file_cli(
    file_path: str,
    *,
    remote_host: str = None,
    remote_port: int = None,
    max_inflight: int = 32,   # argv[4]: parallel chunk-streams in-flight
    on_progress=None,   # kept for drop-in API compat; silently ignored
) -> bool:
    """
    Invoke c_ver/sender to transfer one file over QUIC (MsQuic).

    Binary invocation:
        ./sender  <file_path>  <remote_host>  <remote_port>
                  argv[1]      argv[2]         argv[3]

    Argument sourcing (all from AppConfig/.env when not passed explicitly):
        file_path   → os.path.abspath(file_path)   (always absolute)
        remote_host → config.dest_host              (.env DEST_HOST)
        remote_port → config.port                   (.env PORT, default 4433)

    The sender binary uses QUIC_CREDENTIAL_FLAG_NO_CERTIFICATE_VALIDATION —
    no cert arguments are needed or passed.

    Returns:
        True  — sender exited 0 (transfer complete)
        False — sender exited non-zero (QUIC error; see stderr in logs)

    Note: on_progress is accepted but ignored. Progress tracking is handled
    by Flask's time-estimate based /transfer_status endpoint.
    """
    _check_binaries()
    config = get_config()

    host = remote_host or config.dest_host
    port = int(remote_port or config.port or AppConfig.QUIC_PORT)

    if not host:
        raise ValueError(
            "remote_host not provided and DEST_HOST is not set in .env"
        )

    abs_path = os.path.abspath(file_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"File not found: {abs_path}")

    cmd = [str(SENDER_BIN), abs_path, host, str(port), str(max_inflight)]
    print(f"[quic_cli] sender cmd: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=str(APP_DIR))
    if result.returncode != 0:
        print(f"[quic_cli] sender exited {result.returncode} — transfer may have failed")
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Public API — receiver
# ---------------------------------------------------------------------------

def start_receiver_cli(
    save_path: str,
    *,
    port: int = None,
) -> subprocess.Popen:
    """
    Start c_ver/receiver as a background subprocess for one file transfer.

    Binary invocation:
        ./receiver  <port>   <save_path>
                    argv[1]  argv[2]

    Argument sourcing (all from AppConfig/.env when not passed explicitly):
        port      → config.port     (.env PORT, default 4433)
        save_path → absolute output file path, computed by the /prepare_receive
                    handler from config.out_dir (.env OUTDIR) + filename

    Cert staging: _ensure_certs_staged() copies
        config.key   (.env KEY)   → APP_DIR/server.key
        config.certi (.env CERTI) → APP_DIR/server.crt
    so the binary (cwd=APP_DIR) finds them at the hardcoded relative paths.

    Returns:
        subprocess.Popen — caller must .wait() or .terminate() the process.
    """
    _check_binaries()
    _ensure_certs_staged()   # copy app live certs → APP_DIR/server.{key,crt}

    config = get_config()
    bind_port = int(port or config.port or AppConfig.QUIC_PORT)
    abs_save  = os.path.abspath(save_path)

    # Ensure the output directory exists before the binary tries to write
    os.makedirs(os.path.dirname(abs_save) or str(APP_DIR), exist_ok=True)

    cmd = [str(RECEIVER_BIN), str(bind_port), abs_save]
    print(f"[quic_cli] receiver cmd: {' '.join(cmd)}")

    proc = subprocess.Popen(cmd, cwd=str(APP_DIR))
    return proc
