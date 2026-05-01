#!/usr/bin/env bash
# =================================================
# LANFXplorer — 32-bit App Launcher
# Uses the standalone Python + OpenSSL built by install32.sh
# =================================================

set -e

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
  -h, --help                Show this help

Examples:
  $0 --password mypass123
  $0 -p secret -n "OldLaptop" -o /tmp/received
  $0                          # Uses all defaults (no password)
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

while [ $# -gt 0 ]; do
  case "$1" in
    -p|--password) CLI_PASSWORD="$2"; shift 2 ;;
    -n|--name)     CLI_NAME="$2";     shift 2 ;;
    -o|--outdir)   CLI_OUTDIR="$2";   shift 2 ;;
    -P|--port)     CLI_PORT="$2";     shift 2 ;;
    -h|--help)     usage ;;
    *)             echo "[!] Unknown option: $1"; usage ;;
  esac
done

# -------------------------------------------------
# Resolve paths
# -------------------------------------------------
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

OPT_DIR="$APP_DIR/opt"
PY_PREFIX="$OPT_DIR/python39"
OPENSSL_PREFIX="$OPT_DIR/openssl"

# -------------------------------------------------
# Locate built Python
# -------------------------------------------------
PYTHON="$PY_PREFIX/bin/python3"

if [ ! -x "$PYTHON" ]; then
  echo "[✗] Standalone Python not found at: $PYTHON"
  echo "    Please run install32.sh first to build Python + OpenSSL."
  exit 1
fi

# -------------------------------------------------
# Detect lib vs lib64 for OpenSSL
# -------------------------------------------------
if [ -d "$OPENSSL_PREFIX/lib64" ] && [ ! -d "$OPENSSL_PREFIX/lib" ]; then
  OPENSSL_LIB="$OPENSSL_PREFIX/lib64"
else
  OPENSSL_LIB="$OPENSSL_PREFIX/lib"
fi

# -------------------------------------------------
# Set up Python environment
# -------------------------------------------------
export PYTHONPATH="$APP_DIR"
export LD_LIBRARY_PATH="$OPENSSL_LIB:${LD_LIBRARY_PATH:-}"

# -------------------------------------------------
# Apply CLI overrides as environment variables
# -------------------------------------------------

# Password → set via config_manager (keyring/env fallback)
if [ -n "$CLI_PASSWORD" ]; then
  echo "[+] Setting password from CLI"
  export LANFX_PASSWORD="$CLI_PASSWORD"
fi

# Device name
if [ -n "$CLI_NAME" ]; then
  echo "[+] Device name: $CLI_NAME"
  export LANFX_NAME="$CLI_NAME"
fi

# Output directory
if [ -n "$CLI_OUTDIR" ]; then
  mkdir -p "$CLI_OUTDIR"
  echo "[+] Output directory: $CLI_OUTDIR"
  export LANFX_OUTDIR="$CLI_OUTDIR"
  export LANFX_SRCDIR="$CLI_OUTDIR"
fi

# Port
if [ -n "$CLI_PORT" ]; then
  echo "[+] QUIC port: $CLI_PORT"
  export LANFX_PORT="$CLI_PORT"
fi

# -------------------------------------------------
# Show config summary
# -------------------------------------------------
echo ""
echo "================================================"
echo "  LANFXplorer 32-bit"
echo "================================================"
echo "  App dir  : $APP_DIR"
echo "  Python   : $("$PYTHON" --version 2>&1)"
echo "  OpenSSL  : $($OPENSSL_PREFIX/bin/openssl version 2>/dev/null || echo 'built')"
echo "  Password : ${CLI_PASSWORD:+(set)}${CLI_PASSWORD:-(not set)}"
echo "  Name     : ${CLI_NAME:-$USER}"
echo "  Output   : ${CLI_OUTDIR:-~/Lanfxplorer}"
echo "  Port     : ${CLI_PORT:-4433}"
echo "================================================"
echo ""

# -------------------------------------------------
# Launch
# -------------------------------------------------
exec "$PYTHON" "$APP_DIR/main.py"
