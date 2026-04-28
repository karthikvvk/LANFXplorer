#!/usr/bin/env bash
# =============================================================
# LANFXplorer Service Installer
#
# Installs and enables the systemd user service so LANFXplorer
# starts automatically on login and runs in the background.
#
# Usage:
#   ./install_service.sh            # Install & enable
#   ./install_service.sh --remove   # Disable & remove service
#   ./install_service.sh --status   # Show service status
#   ./install_service.sh --logs     # Tail live journal logs
#   ./install_service.sh --restart  # Restart the running service
#
# No sudo required — this uses the systemd USER instance.
# =============================================================

set -e

APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
SERVICE_NAME="lanfxplorer-backend"
SERVICE_FILE="$APP_DIR/scripts/lanfxplorer-backend.service"
UNIT_DIR="$HOME/.config/systemd/user"
INSTALLED_UNIT="$UNIT_DIR/$SERVICE_NAME.service"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/lanfxplorer.desktop"
LOG_DIR="$APP_DIR/logs"

# ── Colour helpers ────────────────────────────────────────────
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"
CYAN="\033[0;36m"; RESET="\033[0m"; BOLD="\033[1m"

ok()   { echo -e "${GREEN}[✓]${RESET} $*"; }
info() { echo -e "${CYAN}[ℹ]${RESET} $*"; }
warn() { echo -e "${YELLOW}[⚠]${RESET} $*"; }
fail() { echo -e "${RED}[✗]${RESET} $*"; }
hdr()  { echo -e "\n${BOLD}${CYAN}$*${RESET}"; }

# ── Subcommand: --status ──────────────────────────────────────
cmd_status() {
  hdr "LANFXplorer Backend Service Status"
  systemctl --user status "$SERVICE_NAME" 2>/dev/null || true
}

# ── Subcommand: --logs ────────────────────────────────────────
cmd_logs() {
  info "Tailing journal for $SERVICE_NAME  (Ctrl+C to stop)"
  journalctl --user -u "$SERVICE_NAME" -f
}

# ── Subcommand: --restart ─────────────────────────────────────
cmd_restart() {
  hdr "Restarting LANFXplorer Backend Service"
  systemctl --user restart "$SERVICE_NAME"
  ok "Service restarted."
  systemctl --user status "$SERVICE_NAME" --no-pager -l 2>/dev/null | head -20 || true
}

# ── Subcommand: --update ──────────────────────────────────────
# Re-copies the unit file (e.g. after upgrading LANFXplorer) without
# going through the full install flow.  Restarts the service automatically.
cmd_update() {
  hdr "Updating LANFXplorer Backend Service Unit"
  if [ ! -f "$SERVICE_FILE" ]; then
    fail "Service template not found: $SERVICE_FILE"
    exit 1
  fi
  mkdir -p "$UNIT_DIR"
  sed "s|__APP_DIR__|$APP_DIR|g" "$SERVICE_FILE" > "$INSTALLED_UNIT"
  ok "Unit file updated: $INSTALLED_UNIT"
  systemctl --user daemon-reload
  ok "Daemon reloaded."
  systemctl --user restart "$SERVICE_NAME" 2>/dev/null || true
  ok "Service restarted."
  systemctl --user status "$SERVICE_NAME" --no-pager -l 2>/dev/null | head -10 || true
}

# ── Subcommand: --remove ──────────────────────────────────────
cmd_remove() {
  hdr "Removing LANFXplorer Backend Service"

  systemctl --user stop "$SERVICE_NAME"    2>/dev/null || true
  systemctl --user disable "$SERVICE_NAME" 2>/dev/null || true

  if [ -f "$INSTALLED_UNIT" ]; then
    rm -f "$INSTALLED_UNIT"
    systemctl --user daemon-reload
    ok "Removed: $INSTALLED_UNIT"
  else
    info "Unit not installed — nothing to remove."
  fi

  # Revert desktop entry back to terminal=true style (uses app.sh)
  if [ -f "$DESKTOP_FILE" ]; then
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=LANFXplorer
Exec=$APP_DIR/app.sh
Icon=network-workgroup
Terminal=true
Type=Application
Categories=Network;Utility;
EOF
    ok "Desktop entry reverted to terminal mode: $DESKTOP_FILE"
  fi

  ok "Service removed. You can re-install with: ./install_service.sh"
}

# ── Subcommand: install (default) ────────────────────────────
cmd_install() {
  hdr "LANFXplorer Service Installer"
  echo -e "  App directory : ${BOLD}$APP_DIR${RESET}"
  echo -e "  Service unit  : ${BOLD}$INSTALLED_UNIT${RESET}"
  echo -e "  Desktop entry : ${BOLD}$DESKTOP_FILE${RESET}"
  echo ""

  # ── Pre-flight checks ──
  if ! command -v systemctl > /dev/null 2>&1; then
    fail "systemctl not found — this system does not use systemd."
    fail "Cannot install a user service without systemd."
    exit 1
  fi

  # Check the user service manager is available
  if ! systemctl --user list-units > /dev/null 2>&1; then
    warn "systemd user instance not available yet."
    warn "Make sure 'loginctl enable-linger $USER' has been run once:"
    echo "    sudo loginctl enable-linger $USER"
    exit 1
  fi

  if [ ! -x "$APP_DIR/lanfxplorer_service.sh" ]; then
    fail "Service entrypoint not found or not executable: $APP_DIR/lanfxplorer_service.sh"
    exit 1
  fi

  # ── Make scripts executable ──
  chmod +x "$APP_DIR/lanfxplorer_service.sh"
  chmod +x "$APP_DIR/lanfxplorer_ui.sh"
  ok "Scripts made executable."

  # ── Create log directory ──
  mkdir -p "$LOG_DIR"
  ok "Log directory: $LOG_DIR"

  # ── Pre-create the systemd working directory ──
  WORK_DIR="$HOME/.local/share/lanfxplorer-workdir"
  mkdir -p "$WORK_DIR"
  ok "Working directory: $WORK_DIR"

  # ── Create systemd user unit directory ──
  mkdir -p "$UNIT_DIR"

  # ── Copy & patch unit file ──
  if [ ! -f "$SERVICE_FILE" ]; then
    fail "Service template not found: $SERVICE_FILE"
    exit 1
  fi

  # Replace the __APP_DIR__ placeholder with the real path
  sed "s|__APP_DIR__|$APP_DIR|g" "$SERVICE_FILE" > "$INSTALLED_UNIT"
  ok "Installed unit: $INSTALLED_UNIT"

  # ── Enable linger so the user service survives logout ──
  if command -v loginctl > /dev/null 2>&1; then
    # loginctl enable-linger requires sudo; skip if already active
    if loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=yes"; then
      ok "Linger already enabled for $USER"
    else
      info "Enabling linger for user $USER (keeps service running after logout)..."
      if sudo loginctl enable-linger "$USER" 2>/dev/null; then
        ok "Linger enabled."
      else
        warn "Could not enable linger (no sudo access?). Service will stop on logout."
        warn "To fix: sudo loginctl enable-linger $USER"
      fi
    fi
  fi

  # ── Reload systemd user daemon ──
  systemctl --user daemon-reload
  ok "Systemd user daemon reloaded."

  # ── Enable (start on login) ──
  systemctl --user enable "$SERVICE_NAME"
  ok "Service enabled (will auto-start on login)."

  # ── Start immediately ──
  info "Starting service now..."
  systemctl --user start "$SERVICE_NAME" || {
    warn "Service start returned non-zero — check logs:"
    warn "  journalctl --user -u $SERVICE_NAME -n 40 --no-pager"
  }

  # ── Wait a moment and verify ──
  sleep 2
  if systemctl --user is-active --quiet "$SERVICE_NAME"; then
    ok "Service is RUNNING."
  else
    warn "Service is NOT running yet — it may still be doing PKI/CA discovery."
    warn "Check status with: systemctl --user status $SERVICE_NAME"
  fi

  # ── Install (or update) desktop entry ──
  mkdir -p "$DESKTOP_DIR"
  cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.1
Type=Application
Name=LANFXplorer
GenericName=LAN File Transfer
Comment=High-speed P2P LAN file transfer over QUIC. Backend service auto-starts; this opens the UI only.
Exec=$APP_DIR/lanfxplorer_ui.sh
Icon=$APP_DIR/lanfxplorery.png
Terminal=false
StartupNotify=true
StartupWMClass=lanfxplorer
Categories=Network;FileTransfer;Utility;
Keywords=LAN;file;transfer;QUIC;P2P;share;
EOF
  chmod +x "$DESKTOP_FILE"
  ok "Desktop entry installed (Terminal=false): $DESKTOP_FILE"

  # Notify the desktop about the changed entry
  if command -v update-desktop-database > /dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
  fi

  # ── Final summary ──
  echo ""
  echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════${RESET}"
  echo -e "${BOLD}${GREEN}  LANFXplorer service installed successfully!${RESET}"
  echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════${RESET}"
  echo ""
  echo -e "  ${BOLD}Service commands:${RESET}"
  echo "    Status  : systemctl --user status  $SERVICE_NAME"
  echo "    Stop    : systemctl --user stop    $SERVICE_NAME"
  echo "    Start   : systemctl --user start   $SERVICE_NAME"
  echo "    Restart : systemctl --user restart $SERVICE_NAME"
  echo "    Disable : systemctl --user disable $SERVICE_NAME"
  echo "    Logs    : journalctl --user -u $SERVICE_NAME -f"
  echo ""
  echo -e "  ${BOLD}Shortcut:${RESET}"
  echo "    ./install_service.sh --status"
  echo "    ./install_service.sh --logs"
  echo "    ./install_service.sh --restart"
  echo "    ./install_service.sh --remove"
  echo ""
  echo -e "  ${BOLD}The desktop icon no longer opens a terminal window.${RESET}"
  echo -e "  ${BOLD}The backend keeps running even when you close the UI.${RESET}"
  echo ""
}

# ── Main ──────────────────────────────────────────────────────
case "${1:-}" in
  --remove)  cmd_remove  ;;
  --status)  cmd_status  ;;
  --logs)    cmd_logs    ;;
  --restart) cmd_restart ;;
  --update)  cmd_update  ;;
  --help|-h)
    echo "Usage: $0 [--remove | --status | --logs | --restart | --update | --help]"
    echo "  (no args) = install & enable the backend service"
    echo "  --update  = re-copy unit file after an app upgrade (no full reinstall)"
    ;;
  *)         cmd_install ;;
esac
