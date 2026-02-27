#!/usr/bin/env bash
set -e

# =================================================
# LANFXplorer — Unified Application Launcher
# 64-bit: Flutter UI  |  32-bit: Python UI → headless
# =================================================

# -------------------------------------------------
# Usage / Help
# -------------------------------------------------
usage() {
  cat <<HELP
Usage: $0 [OPTIONS]

Options:
  -p, --password PASSWORD   Set the peer authentication password
  -n, --name     NAME       Set device/user display name (default: \$USER)
  -o, --outdir   PATH       Set file receive directory (default: ~/Lanfxplorer)
  -P, --port     PORT       Set QUIC port (default: 4433)
      --headless            Force headless mode (no UI, even on 64-bit)
  -h, --help                Show this help

Examples:
  $0                            # Normal launch (UI on 64-bit, headless on 32-bit)
  $0 --password mypass123       # Set password via CLI
  $0 -p secret -n "MyPC"       # Password + custom name
  $0 --headless -p pass123     # Force headless on any arch
HELP
  exit 0
}

# -------------------------------------------------
# Parse CLI arguments
# -------------------------------------------------
CLI_PASSWORD=""
CLI_NAME=""
CLI_OUTDIR=""
CLI_PORT=""
FORCE_HEADLESS=""

while [ $# -gt 0 ]; do
  case "$1" in
    -p|--password)  CLI_PASSWORD="$2"; shift 2 ;;
    -n|--name)      CLI_NAME="$2";     shift 2 ;;
    -o|--outdir)    CLI_OUTDIR="$2";   shift 2 ;;
    -P|--port)      CLI_PORT="$2";     shift 2 ;;
    --headless)     FORCE_HEADLESS=1;  shift ;;
    -h|--help)      usage ;;
    *)              echo "[!] Unknown option: $1"; usage ;;
  esac
done

# -------------------------------------------------
# Resolve paths
# -------------------------------------------------
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

OPENSSL_PREFIX="$APP_DIR/opt/openssl"
PY_PREFIX="$APP_DIR/opt/python39"

# Detect lib vs lib64 for OpenSSL
if [ -d "$OPENSSL_PREFIX/lib64" ] && [ ! -d "$OPENSSL_PREFIX/lib" ]; then
  OPENSSL_LIB="$OPENSSL_PREFIX/lib64"
else
  OPENSSL_LIB="$OPENSSL_PREFIX/lib"
fi

# -------------------------------------------------
# Set up Python environment
# -------------------------------------------------
export PATH="$PY_PREFIX/bin:$PATH"
export LD_LIBRARY_PATH="$OPENSSL_LIB:$PY_PREFIX/lib:$LD_LIBRARY_PATH"
export PYTHONHOME="$PY_PREFIX"
export PYTHONPATH="$APP_DIR"

# Source Rust/Cargo if available (needed for some pip builds on 32-bit)
if [ -f "$HOME/.cargo/env" ]; then
  source "$HOME/.cargo/env"
fi

# -------------------------------------------------
# Architecture auto-detection
# -------------------------------------------------
HOST_ARCH="$(uname -m)"
ARCH_BITS=64
if [ "$HOST_ARCH" = "i686" ] || [ "$HOST_ARCH" = "i386" ]; then
  ARCH_BITS=32
  # 32-bit: Flutter UI won't work (x64 only) but main.py will
  # try Python UI (tkinter) first, then fall back to headless CLI
  # Point Rust to our custom OpenSSL (for pip rebuilds)
  export OPENSSL_DIR="$OPENSSL_PREFIX"
  export OPENSSL_LIB_DIR="$OPENSSL_LIB"
  export OPENSSL_INCLUDE_DIR="$OPENSSL_PREFIX/include"
  export CARGO_BUILD_TARGET=i686-unknown-linux-gnu
fi

# -------------------------------------------------
# Apply CLI overrides as environment variables
# -------------------------------------------------
if [ -n "$FORCE_HEADLESS" ]; then
  export LANFXPLORER_HEADLESS=1
fi

if [ -n "$CLI_PASSWORD" ]; then
  export PASSWORD="$CLI_PASSWORD"
fi

if [ -n "$CLI_NAME" ]; then
  export USER="$CLI_NAME"
fi

if [ -n "$CLI_OUTDIR" ]; then
  mkdir -p "$CLI_OUTDIR"
  export OUTDIR="$CLI_OUTDIR"
  export SRCDIR="$CLI_OUTDIR"
fi

if [ -n "$CLI_PORT" ]; then
  export PORT="$CLI_PORT"
fi

# -------------------------------------------------
# Config summary (only when CLI args are used)
# -------------------------------------------------
if [ -n "$CLI_PASSWORD" ] || [ -n "$CLI_NAME" ] || [ -n "$CLI_OUTDIR" ] || [ -n "$CLI_PORT" ] || [ -n "$FORCE_HEADLESS" ]; then
  echo ""
  echo "================================================"
  echo "  LANFXplorer (${ARCH_BITS}-bit${FORCE_HEADLESS:+ — headless})"
  echo "================================================"
  [ -n "$CLI_PASSWORD" ] && echo "  Password : (set)"
  [ -n "$CLI_NAME" ]     && echo "  Name     : $CLI_NAME"
  [ -n "$CLI_OUTDIR" ]   && echo "  Output   : $CLI_OUTDIR"
  [ -n "$CLI_PORT" ]     && echo "  Port     : $CLI_PORT"
  echo "================================================"
  echo ""
fi

# -------------------------------------------------
# Launch
# -------------------------------------------------
exec "$PY_PREFIX/bin/python3" "$APP_DIR/main.py"
