#!/usr/bin/env bash
# =============================================================
# LANFXplorer Backend Service Entrypoint
#
# Launched by systemd user service (lanfxplorer-backend.service).
# Runs the full backend stack (startsetup → receive → api_bridge)
# in headless mode.  The Flutter UI connects to this running
# backend via the Flask API; it does NOT need to restart the
# backend.
#
# Environment variables that systemd cannot inject automatically
# (D-Bus session, keyring, display server) are sourced here so
# that the keyring / gnome-keyring integration continues to work
# even under a user service without a full desktop session.
# =============================================================

# Do NOT use set -e in a long-running service entrypoint.
# A transient error (cargo env missing, D-Bus probe, etc.) must NOT kill the
# service — only a missing Python binary is truly fatal.

# ------------------------------------------------------------------
# Resolve application directory from this script's real location
# ------------------------------------------------------------------
APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

# ------------------------------------------------------------------
# Bundled Python & OpenSSL paths
# ------------------------------------------------------------------
PY_PREFIX="$APP_DIR/opt/python39"
OPENSSL_PREFIX="$APP_DIR/opt/openssl"

if [ -d "$OPENSSL_PREFIX/lib64" ] && [ ! -d "$OPENSSL_PREFIX/lib" ]; then
  OPENSSL_LIB="$OPENSSL_PREFIX/lib64"
else
  OPENSSL_LIB="$OPENSSL_PREFIX/lib"
fi

if [ ! -x "$PY_PREFIX/bin/python3" ]; then
  echo "[lanfxplorer-svc] FATAL: bundled Python not found at $PY_PREFIX" >&2
  echo "[lanfxplorer-svc] Run ./install.sh first to complete installation." >&2
  exit 1
fi

# Ensure the systemd working directory exists (belt-and-suspenders alongside ExecStartPre)
mkdir -p "$HOME/.local/share/lanfxplorer-workdir" || true

# ------------------------------------------------------------------
# Set up environment
# ------------------------------------------------------------------
export PATH="$PY_PREFIX/bin:$PATH"

case ":${LD_LIBRARY_PATH}:" in
  *":$OPENSSL_LIB:"*) ;;
  *) export LD_LIBRARY_PATH="$OPENSSL_LIB:$PY_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ;;
esac

export PYTHONHOME="$PY_PREFIX"
export PYTHONPATH="$APP_DIR"

# Headless mode: suppress Flutter / Tkinter UI launch inside main.py
export LANFXPLORER_HEADLESS=1

# Source Rust/Cargo if needed (some pip packages require it at runtime).
# Deliberately ignoring errors — cargo is not required for LANFXplorer itself.
if [ -f "$HOME/.cargo/env" ]; then
  # shellcheck source=/dev/null
  source "$HOME/.cargo/env" 2>/dev/null || true
fi

# ------------------------------------------------------------------
# D-Bus / keyring availability for user services
#
# systemd user services may run before the graphical session fully
# initialises its D-Bus session bus.  We try to inherit the session
# bus address from the systemd user environment.  If that fails we
# fall back to a dbus-run-session wrapper so gnome-keyring / kwallet
# is accessible (password storage).
# ------------------------------------------------------------------
if [ -z "$DBUS_SESSION_BUS_ADDRESS" ]; then
  # Try to pull it from the running systemd user environment.
  # This is a best-effort probe — failure is non-fatal (keyring may not be needed).
  _DBUS_LINE="$(systemctl --user show-environment 2>/dev/null | grep '^DBUS_SESSION_BUS_ADDRESS=' | head -1)"
  if [ -n "$_DBUS_LINE" ]; then
    eval "$_DBUS_LINE" || true
  fi
  unset _DBUS_LINE
fi

# Also try to inherit XDG_RUNTIME_DIR if missing (needed for keyring sockets)
if [ -z "$XDG_RUNTIME_DIR" ]; then
  _XDG_LINE="$(systemctl --user show-environment 2>/dev/null | grep '^XDG_RUNTIME_DIR=' | head -1)"
  if [ -n "$_XDG_LINE" ]; then
    eval "$_XDG_LINE" || true
    export XDG_RUNTIME_DIR
  fi
  unset _XDG_LINE
fi

# ------------------------------------------------------------------
# Log startup banner
# ------------------------------------------------------------------
echo "[lanfxplorer-svc] ============================================"
echo "[lanfxplorer-svc] LANFXplorer Backend Service starting up"
echo "[lanfxplorer-svc] PID: $$  |  $(date)"
echo "[lanfxplorer-svc] APP_DIR: $APP_DIR"
echo "[lanfxplorer-svc] Python: $PY_PREFIX/bin/python3"
echo "[lanfxplorer-svc] ============================================"

# ------------------------------------------------------------------
# Launch main.py in headless mode
# This runs startsetup → receive → api_bridge and blocks until
# the service is stopped (SIGTERM from systemd).
# ------------------------------------------------------------------
exec "$PY_PREFIX/bin/python3" "$APP_DIR/main.py"
