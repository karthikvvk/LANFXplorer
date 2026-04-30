#!/usr/bin/env bash
# =============================================================
# LANFXplorer UI Launcher  (Desktop Entry / Menu Item)
#
# This script is called by the .desktop file when the user clicks
# the LANFXplorer icon.  It:
#   1. Ensures the backend service is running (starts it if not).
#   2. Launches ONLY the Flutter UI binary — no terminal window,
#      no CLI output visible to the user.
#
# The backend (receive.py + api_bridge.py) continues running
# independently of the UI window.  Closing the UI window does NOT
# stop the backend service.
# =============================================================

APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
SERVICE_NAME="lanfxplorer-backend.service"

# ------------------------------------------------------------------
# 1. Ensure the systemd user service is active
# ------------------------------------------------------------------
if systemctl --user is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
  echo "[ui-launcher] Backend service already running — OK"
else
  echo "[ui-launcher] Backend service not active — starting it now..."
  systemctl --user start "$SERVICE_NAME" 2>/dev/null || {
    echo "[ui-launcher] WARNING: could not start service via systemctl." >&2
    echo "[ui-launcher] Falling back to direct launch (background)..." >&2
    LANFXPLORER_HEADLESS=1 "$APP_DIR/lanfxplorer_service.sh" \
      >> "$APP_DIR/logs/backend.log" 2>&1 &
    # Give the backend a moment to bind its ports
    sleep 3
  }

  # Wait up to 15 s for API to become responsive
  echo "[ui-launcher] Waiting for API to be ready..."
  for i in $(seq 1 15); do
    if curl -sf "http://127.0.0.1:5000/ping" > /dev/null 2>&1; then
      echo "[ui-launcher] API ready after ${i}s"
      break
    fi
    sleep 1
  done
fi

# ------------------------------------------------------------------
# 2. Detect architecture and locate Flutter binary
# ------------------------------------------------------------------
HOST_ARCH="$(uname -m)"
FLUTTER_BIN=""

case "$HOST_ARCH" in
  x86_64)
    FLUTTER_BIN="$APP_DIR/build/linux/x64/release/bundle/lanfxplorer"
    ;;
  aarch64|arm64)
    FLUTTER_BIN="$APP_DIR/build/linux/arm64/release/bundle/lanfxplorer"
    ;;
esac

# ------------------------------------------------------------------
# 3. Launch UI
# ------------------------------------------------------------------
if [ -n "$FLUTTER_BIN" ] && [ -x "$FLUTTER_BIN" ]; then
  echo "[ui-launcher] Launching Flutter UI: $FLUTTER_BIN"
  # Run without exec so this script can do post-close cleanup later
  "$FLUTTER_BIN"
  UI_EXIT=$?
  echo "[ui-launcher] Flutter UI exited (code $UI_EXIT) — backend continues running."
else
  # Fallback: Tkinter UI (32-bit or flutter binary missing)
  echo "[ui-launcher] Flutter binary not found — trying Tkinter UI..."
  PY_PREFIX="$APP_DIR/opt/python39"
  OPENSSL_PREFIX="$APP_DIR/opt/openssl"

  if [ -d "$OPENSSL_PREFIX/lib64" ] && [ ! -d "$OPENSSL_PREFIX/lib" ]; then
    OPENSSL_LIB="$OPENSSL_PREFIX/lib64"
  else
    OPENSSL_LIB="$OPENSSL_PREFIX/lib"
  fi

  export PATH="$PY_PREFIX/bin:$PATH"
  case ":${LD_LIBRARY_PATH}:" in
    *":$OPENSSL_LIB:"*) ;;
    *) export LD_LIBRARY_PATH="$OPENSSL_LIB:$PY_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ;;
  esac
  export PYTHONHOME="$PY_PREFIX"
  export PYTHONPATH="$APP_DIR"

  if [ -x "$PY_PREFIX/bin/python3" ]; then
    "$PY_PREFIX/bin/python3" -c "
import sys
sys.path.insert(0, '$APP_DIR/32bitscreens')
import tkinter_app
tkinter_app.main()
" 2>&1
  else
    echo "[ui-launcher] ERROR: No UI available (no Flutter binary, no bundled Python)." >&2
    # Show a graphical error so user sees something meaningful
    if command -v zenity > /dev/null 2>&1; then
      zenity --error \
        --title="LANFXplorer" \
        --text="LANFXplorer backend is running but the UI binary was not found.\n\nThe backend service is still active for file transfers.\n\nRun install.sh to rebuild the UI." 2>/dev/null || true
    fi
    exit 1
  fi
fi
