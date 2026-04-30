#!/usr/bin/env bash
# =================================================
# LANFXplorer — Application Launcher (64-bit Linux)
# Uses system Python — no standalone opt/ builds needed.
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
      --headless            Force headless mode (no UI)
  -h, --help                Show this help

Examples:
  $0                            # Normal launch
  $0 --password mypass123       # Set password via CLI
  $0 -p secret -n "MyPC"        # Password + custom name
  $0 --headless -p pass123      # Force headless
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

# -------------------------------------------------
# Verify system Python exists
# -------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "[✗] python3 not found. Please install Python 3.8+:"
  echo "    sudo apt install python3 python3-pip   # Debian/Ubuntu"
  echo "    sudo dnf install python3 python3-pip   # Fedora"
  exit 1
fi

# -------------------------------------------------
# Set up PYTHONPATH so local modules resolve
# -------------------------------------------------
export PYTHONPATH="$APP_DIR"

# Source Cargo env if available (only needed on 32-bit for cryptography source build)
if [ -f "$HOME/.cargo/env" ]; then
  source "$HOME/.cargo/env" || true
fi

# -------------------------------------------------
# Apply CLI overrides as namespaced environment vars
# -------------------------------------------------
if [ -n "$FORCE_HEADLESS" ]; then
  export LANFXPLORER_HEADLESS=1
fi
if [ -n "$CLI_PASSWORD" ]; then
  export LANFX_PASSWORD="$CLI_PASSWORD"
fi
if [ -n "$CLI_NAME" ]; then
  export LANFX_NAME="$CLI_NAME"
fi
if [ -n "$CLI_OUTDIR" ]; then
  mkdir -p "$CLI_OUTDIR"
  export LANFX_OUTDIR="$CLI_OUTDIR"
  export LANFX_SRCDIR="$CLI_OUTDIR"
fi
if [ -n "$CLI_PORT" ]; then
  export LANFX_PORT="$CLI_PORT"
fi

# -------------------------------------------------
# Config summary (only when CLI args were given)
# -------------------------------------------------
if [ -n "$CLI_PASSWORD" ] || [ -n "$CLI_NAME" ] || \
   [ -n "$CLI_OUTDIR" ]   || [ -n "$CLI_PORT" ] || \
   [ -n "$FORCE_HEADLESS" ]; then
  echo ""
  echo "================================================"
  echo "  LANFXplorer${FORCE_HEADLESS:+ — headless}"
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
python3 "$APP_DIR/main.py"
EXIT_CODE=$?
exit $EXIT_CODE