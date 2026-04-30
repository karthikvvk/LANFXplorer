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
# Python: use venv absolute path — NO source activate needed.
# Direct binary path → sys.executable inside main.py is the venv Python
# → ALL child processes inherit the venv packages automatically.
# ------------------------------------------------------------------
VENV_PYTHON="$APP_DIR/virtual/bin/python"

if [ -x "$VENV_PYTHON" ]; then
  PYTHON="$VENV_PYTHON"
else
  echo "[lanfxplorer-svc] FATAL: venv not found at $VENV_PYTHON" >&2
  echo "[lanfxplorer-svc] Run ./install.sh first to create the virtual environment." >&2
  exit 1
fi

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
echo "[lanfxplorer-svc] Python:  $($PYTHON --version 2>&1)"
echo "[lanfxplorer-svc] ============================================"

# ------------------------------------------------------------------
# Launch main.py in headless mode
# This runs startsetup → receive → api_bridge and blocks until
# the service is stopped (SIGTERM from systemd).
# ------------------------------------------------------------------
exec "$PYTHON" "$APP_DIR/main.py"
