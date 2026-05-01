#!/usr/bin/env bash
set -e

# =================================
# LANFXplorer — Linux 64-bit (x86_64) Installer
# Standalone Python/OpenSSL builds removed — aioquic is gone.
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

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TESTING_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$APP_DIR/.env"

# Load .env
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
# System pip dependencies
# ===============================
DEPS="python3 curl"

install_deps() {
  echo "[+] Installing system dependencies: $DEPS + tkinter (dev)"
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y $DEPS python3-tk
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y $DEPS python3-tkinter
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y $DEPS python3-tkinter
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm python python-pip curl tk
  elif command -v apk >/dev/null 2>&1; then
    sudo apk add python3 py3-pip curl python3-tkinter tk
  else
    echo "[!] No supported package manager found."
    echo "    Please install manually: python3 curl python3-tk"
    echo "    (pip is NOT needed system-wide — the venv provides its own pip)"
    exit 1
  fi
}



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




# Only python3 needs to be present system-wide.
# pip3 excluded: modern distros block system-wide pip (PEP 668).
# The venv created below supplies its own pip via ensurepip.
MISSING=""
for dep in python3; do
  if ! command -v "$dep" >/dev/null 2>&1; then
    MISSING="$MISSING $dep"
  fi
done

if [ -n "$MISSING" ]; then
  echo "[!] Missing dependencies:$MISSING"
  install_deps
else
  echo "[✓] python3 present (venv will supply pip)"
fi

# ===============================
# pip + 64-bit requirements
# ===============================
echo "[+] Upgrading pip and installing 64-bit dependencies"
"$PIP" install --upgrade pip
"$PIP" install -r "$TESTING_DIR/requirements_64.txt"

# Install dev requirements if present (optional developer extras)
if [ -f "$APP_DIR/dev_requirements.txt" ]; then
  echo "[+] dev_requirements.txt found — installing dev extras"
  "$PIP" install -r "$APP_DIR/dev_requirements.txt"
else
  echo "[i] No dev_requirements.txt found — skipping dev extras"
fi

echo "[✓] Dependencies installed"

# ===============================
# Runtime directories
# ===============================
mkdir -p "$APP_DIR/data" "$APP_DIR/logs"

# ===============================
# Desktop entry
# ===============================
DESKTOP_FILE="$HOME/.local/share/applications/lanfxplorer.desktop"
mkdir -p "$(dirname "$DESKTOP_FILE")"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=LANFXplorer
Exec=$APP_DIR/app.sh
Icon=network-workgroup
Terminal=true
Type=Application
Categories=Network;Utility;
EOF

chmod +x "$DESKTOP_FILE"
touch "$APP_DIR/.installed"

# Mark install complete
if grep -q "^INSTALLER=" "$ENV_FILE" 2>/dev/null; then
  sed -i "s/^INSTALLER=.*/INSTALLER='true'/" "$ENV_FILE"
else
  echo "INSTALLER='true'" >> "$ENV_FILE"
fi

echo ""
echo "================================================"
echo "[✓] 64-bit Installation complete"
echo "    Python: $($PYTHON --version)"
echo "    cryptography: bundles own OpenSSL via cffi"
echo "================================================"

chmod +x "$APP_DIR/app.sh"
# "$APP_DIR/app.sh"
exec "$APP_DIR/app.sh"