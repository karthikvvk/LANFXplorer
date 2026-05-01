#!/usr/bin/env bash
set -e

# =================================
# LANFXplorer — Linux 64-bit Installer
# Uses system Python + pip — no standalone builds needed.
# cryptography pip package bundles its own OpenSSL via cffi.
# =================================

# Terminal Detection & Re-launch
if [ ! -t 0 ] && [ -z "$LANFXPLORER_IN_TERMINAL" ]; then
  SCRIPT_PATH="$(readlink -f "$0")"
  TERMINAL_CMD=""
  if command -v gnome-terminal >/dev/null 2>&1; then
    TERMINAL_CMD="gnome-terminal -- bash -c"
  elif command -v konsole >/dev/null 2>&1; then
    TERMINAL_CMD="konsole -e bash -c"
  elif command -v xfce4-terminal >/dev/null 2>&1; then
    TERMINAL_CMD="xfce4-terminal -e bash -c"
  elif command -v xterm >/dev/null 2>&1; then
    TERMINAL_CMD="xterm -e bash -c"
  elif command -v lxterminal >/dev/null 2>&1; then
    TERMINAL_CMD="lxterminal -e bash -c"
  elif command -v mate-terminal >/dev/null 2>&1; then
    TERMINAL_CMD="mate-terminal -e bash -c"
  fi
  if [ -n "$TERMINAL_CMD" ]; then
    export LANFXPLORER_IN_TERMINAL=1
    exec $TERMINAL_CMD "export LANFXPLORER_IN_TERMINAL=1; '$SCRIPT_PATH'; echo; read -p 'Press Enter to close...'"
  else
    echo "[!] No supported terminal emulator found. Running without terminal."
  fi
fi

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$APP_DIR/.env"

# Load .env safely
if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

# If already installed → run app
INSTALLER_FLAG="${INSTALLER:-false}"
INSTALLER_FLAG="$(echo "$INSTALLER_FLAG" | tr '[:upper:]' '[:lower:]')"
if [ "$INSTALLER_FLAG" = "true" ]; then
  exec "$APP_DIR/app.sh"
fi

# ===============================
# System dependencies
# (cmake + libmsquic-dev for MsQuic build; keyring for SecretStorage)
# ===============================
DEPS="python3 curl cmake"

install_deps() {
  echo "[+] Installing system dependencies: $DEPS + keyring backend + tkinter (dev)"
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y $DEPS gnome-keyring libsecret-1-0 libsecret-1-dev python3-tk
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y $DEPS gnome-keyring libsecret libsecret-devel python3-tkinter
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y $DEPS gnome-keyring libsecret libsecret-devel python3-tkinter
  elif command -v xbps-install >/dev/null 2>&1; then
    sudo xbps-install -Sy $DEPS gnome-keyring libsecret libsecret-devel python3-tkinter
  elif command -v zypper >/dev/null 2>&1; then
    sudo zypper install -y $DEPS gnome-keyring libsecret-devel python3-tk
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm $DEPS gnome-keyring libsecret tk
  elif command -v apk >/dev/null 2>&1; then
    sudo apk add $DEPS gnome-keyring libsecret-dev python3-tkinter tk
  else
    echo "[!] No supported package manager found."
    echo "    Please install manually: python3 cmake gnome-keyring libsecret python3-tk"
    echo "    (pip is NOT needed system-wide — the venv provides its own pip)"
    exit 1
  fi
}

# Only python3 itself needs to be present system-wide.
# pip3 is intentionally excluded: modern distros (Arch, Ubuntu 23+) block
# system-wide pip (PEP 668). The venv we create below has its own pip.
MISSING=""
for dep in python3 cmake; do
  if ! command -v "$dep" >/dev/null 2>&1; then
    MISSING="$MISSING $dep"
  fi
done

if [ -n "$MISSING" ]; then
  echo "[!] Missing dependencies:$MISSING"
  install_deps
else
  echo "[✓] System dependencies already present"
fi

# ===============================
# ===============================
# Create / reuse virtual environment
# ===============================
VENV_DIR="$APP_DIR/virtual"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "[+] Creating Python virtual environment: $VENV_DIR"
  python3 -m venv "$VENV_DIR"
  echo "[✓] Virtual environment created"
else
  echo "[✓] Virtual environment already exists"
fi
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

# ===============================
# pip + Python requirements
# ===============================
echo "[+] Upgrading pip and installing Python requirements"
"$PIP" install --upgrade pip
"$PIP" install -r "$APP_DIR/requirements.txt"

# Install dev requirements if present (optional developer extras)
if [ -f "$APP_DIR/dev_requirements.txt" ]; then
  echo "[+] dev_requirements.txt found — installing dev extras"
  "$PIP" install -r "$APP_DIR/dev_requirements.txt"
else
  echo "[i] No dev_requirements.txt found — skipping dev extras"
fi

echo "[✓] Python requirements installed"

# ===============================
# Build MsQuic CLI binaries → binaries/
# ===============================
echo "[+] Building MsQuic CLI binaries (sender, receiver) → $APP_DIR/binaries"

if ! ldconfig -p 2>/dev/null | grep -q libmsquic; then
  echo "[!] WARNING: libmsquic not found in system libraries."
  echo "    Install MsQuic from: https://github.com/microsoft/msquic/releases"
  echo "    or via: sudo apt install libmsquic (if your distro packages it)"
  echo "    Skipping binary build — transfer will fail until libmsquic is installed."
else
  CVER_DIR="$APP_DIR/c_ver"
  BIN_DIR="$APP_DIR/binaries"
  mkdir -p "$BIN_DIR"
  cmake -B "$CVER_DIR/build" -DCMAKE_BUILD_TYPE=Release "$CVER_DIR" && \
  cmake --build "$CVER_DIR/build" && \
  cp "$CVER_DIR/build/sender"   "$BIN_DIR/sender" && \
  cp "$CVER_DIR/build/receiver" "$BIN_DIR/receiver" && \
  chmod +x "$BIN_DIR/sender" "$BIN_DIR/receiver" && \
  echo "[✓] MsQuic binaries installed: $BIN_DIR/sender  $BIN_DIR/receiver" || \
  echo "[!] MsQuic binary build failed — check cmake output above."
fi

# ===============================
# Firewall rules
# ===============================
echo "[+] Configuring firewall rules for LANFXplorer..."
"$PYTHON" "$APP_DIR/firewall_manager.py" --install || {
  echo "[!] Firewall configuration failed (non-fatal). You may need to manually allow ports."
}

# ===============================
# Sudoers rule — passwordless ip addr
# ===============================
if [ -d /etc/sudoers.d ]; then
  SUDOERS_FILE="/etc/sudoers.d/lanfxplorer-ip"
  CURRENT_USER="$(whoami)"
  SUDOERS_RULE="$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/ip addr *"
  if [ -f "$SUDOERS_FILE" ] && grep -qF "$SUDOERS_RULE" "$SUDOERS_FILE" 2>/dev/null; then
    echo "[✓] Sudoers rule already present ($SUDOERS_FILE)"
  else
    echo "[+] Adding passwordless sudoers rule for 'ip addr' (user: $CURRENT_USER)..."
    echo "$SUDOERS_RULE" | sudo tee "$SUDOERS_FILE" > /dev/null
    sudo chmod 440 "$SUDOERS_FILE"
    echo "[✓] Sudoers rule added: $SUDOERS_FILE"
  fi
else
  echo "[!] /etc/sudoers.d not found — skipping ip addr sudoers rule"
fi

# ===============================
# Runtime directories
# ===============================
mkdir -p "$APP_DIR/data" "$APP_DIR/logs"

# ===============================
# Make scripts executable
# ===============================
chmod +x "$APP_DIR/lanfxplorer_service.sh" 2>/dev/null || true
chmod +x "$APP_DIR/app.sh"                 2>/dev/null || true
chmod +x "$APP_DIR/install_service.sh"     2>/dev/null || true
chmod +x "$APP_DIR/lanfxplorer_ui.sh"      2>/dev/null || true

# ===============================
# Desktop entry
# ===============================
DESKTOP_FILE="$HOME/.local/share/applications/lanfxplorer.desktop"
mkdir -p "$(dirname "$DESKTOP_FILE")"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.1
Type=Application
Name=LANFXplorer
GenericName=LAN File Transfer
Comment=High-speed P2P LAN file transfer over QUIC.
Exec=$APP_DIR/app.sh
Icon=$APP_DIR/lanfxplorery.png
Terminal=false
StartupNotify=true
StartupWMClass=lanfxplorer
Categories=Network;FileTransfer;Utility;
Keywords=LAN;file;transfer;QUIC;P2P;share;
EOF

chmod +x "$DESKTOP_FILE"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$(dirname "$DESKTOP_FILE")" 2>/dev/null || true
fi
touch "$APP_DIR/.installed"

# ===============================
# Mark installation as complete
# ===============================
if grep -q "^INSTALLER=" "$ENV_FILE" 2>/dev/null; then
  sed -i "s/^INSTALLER=.*/INSTALLER='true'/" "$ENV_FILE"
else
  echo "INSTALLER='true'" >> "$ENV_FILE"
fi

echo "[✓] Installation complete"

# ===============================
# Install systemd user service
# ===============================
echo ""
echo "[+] Installing LANFXplorer systemd user service..."
if command -v systemctl >/dev/null 2>&1 && systemctl --user list-units >/dev/null 2>&1; then
  "$APP_DIR/install_service.sh" || {
    echo "[!] Service installation encountered an issue (non-fatal)."
    echo "    You can install it later with: $APP_DIR/install_service.sh"
    echo "    For now, launching via app.sh (terminal mode)..."
    exec "$APP_DIR/app.sh"
  }
else
  echo "[!] systemd user services not available on this system."
  echo "    Launching via app.sh instead..."
  exec "$APP_DIR/app.sh"
fi

# ===============================
# All done
# ===============================
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║       LANFXplorer installation complete!             ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  The backend service starts automatically on login.  ║"
echo "║  Click the desktop icon (or run app.sh) to open UI. ║"
echo "║  Closing the UI keeps the backend live.              ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Quick management:                                   ║"
echo "║    Status  : ./install_service.sh --status           ║"
echo "║    Logs    : ./install_service.sh --logs             ║"
echo "║    Restart : ./install_service.sh --restart          ║"
echo "║    Remove  : ./install_service.sh --remove           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

exec "$APP_DIR/app.sh"