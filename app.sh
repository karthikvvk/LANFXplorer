#!/usr/bin/env bash
# =================================================
# LANFXplorer — Unified Application Launcher
# 64-bit: Flutter UI  |  32-bit: Python UI → headless
# =================================================

# -------------------------------------------------
# Exit on unhandled errors (but allow graceful
# fallbacks where we explicitly use || true)
# -------------------------------------------------
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
      --headless            Force headless mode (no UI, even on 64-bit)
  -h, --help                Show this help

Examples:
  $0                            # Normal launch (UI on 64-bit, headless on 32-bit)
  $0 --password mypass123       # Set password via CLI
  $0 -p secret -n "MyPC"        # Password + custom name
  $0 --headless -p pass123      # Force headless on any arch
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
# Verify bundled Python exists before doing anything
# -------------------------------------------------
if [ ! -x "$PY_PREFIX/bin/python3" ]; then
  echo "[✗] Python not found at $PY_PREFIX/bin/python3"
  echo "    Run ./install.sh first to set up dependencies."
  exit 1
fi

# -------------------------------------------------
# Set up Python environment
# (Guard against LD_LIBRARY_PATH growing on repeated runs)
# -------------------------------------------------
export PATH="$PY_PREFIX/bin:$PATH"

case ":${LD_LIBRARY_PATH}:" in
  *":$OPENSSL_LIB:"*)
    # OpenSSL path already present — skip to avoid duplicates
    ;;
  *)
    export LD_LIBRARY_PATH="$OPENSSL_LIB:$PY_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    ;;
esac

export PYTHONHOME="$PY_PREFIX"
export PYTHONPATH="$APP_DIR"

# Source Rust/Cargo if available (needed for some pip builds on 32-bit).
# '|| true' prevents set -e from killing the launcher if cargo env fails.
if [ -f "$HOME/.cargo/env" ]; then
  # shellcheck source=/dev/null
  source "$HOME/.cargo/env" || true
fi

# -------------------------------------------------
# Architecture auto-detection
# (covers x86 32-bit AND 32-bit ARM: RPi, armv6/v7)
# -------------------------------------------------
HOST_ARCH="$(uname -m)"
ARCH_BITS=64

case "$HOST_ARCH" in
  i686|i386|armv7l|armv6l)
    ARCH_BITS=32
    # 32-bit: Flutter UI won't work (x64 only). main.py will try
    # the Python/tkinter UI first, then fall back to headless CLI.
    # Point Rust/pip to our bundled OpenSSL for any native rebuilds.
    export OPENSSL_DIR="$OPENSSL_PREFIX"
    export OPENSSL_LIB_DIR="$OPENSSL_LIB"
    export OPENSSL_INCLUDE_DIR="$OPENSSL_PREFIX/include"
    export CARGO_BUILD_TARGET="${HOST_ARCH}-unknown-linux-gnu"
    ;;
esac

# -------------------------------------------------
# Apply CLI overrides as namespaced environment vars
#
# NOTE: LANFX_NAME is used instead of USER because USER is a
# reserved POSIX variable (current login name). Overwriting it
# breaks os.environ["USER"], home-dir resolution, and any library
# that reads USER for ownership/permission checks.
# -------------------------------------------------
if [ -n "$FORCE_HEADLESS" ]; then
  export LANFXPLORER_HEADLESS=1
fi

if [ -n "$CLI_PASSWORD" ]; then
  export LANFX_PASSWORD="$CLI_PASSWORD"
fi

if [ -n "$CLI_NAME" ]; then
  export LANFX_NAME="$CLI_NAME"       # namespaced — never clobbers $USER
fi

if [ -n "$CLI_OUTDIR" ]; then
  mkdir -p "$CLI_OUTDIR"
  export LANFX_OUTDIR="$CLI_OUTDIR"   # namespaced — read via Path() in Python
  export LANFX_SRCDIR="$CLI_OUTDIR"
fi

if [ -n "$CLI_PORT" ]; then
  export LANFX_PORT="$CLI_PORT"
fi

# -------------------------------------------------
# Config summary (only when at least one CLI arg given)
# -------------------------------------------------
if [ -n "$CLI_PASSWORD" ] || [ -n "$CLI_NAME" ] || \
   [ -n "$CLI_OUTDIR" ]   || [ -n "$CLI_PORT" ] || \
   [ -n "$FORCE_HEADLESS" ]; then
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
# Using direct invocation (not exec) so that future
# signal traps or post-exit cleanup can be added here
# without restructuring the script.
"$PY_PREFIX/bin/python3" "$APP_DIR/main.py"
EXIT_CODE=$?

# Post-exit hook: add any cleanup here (log rotation,
# temp file removal, socket cleanup, etc.)
# Example:
#   rm -f "$APP_DIR/run/*.pid"

exit $EXIT_CODE