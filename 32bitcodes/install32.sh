 #!/usr/bin/env bash
set -e

# =================================
# LANFXplorer — Linux 32-bit (i686) Installer
# Standalone Python/OpenSSL builds removed — aioquic is gone.
# cryptography pip package bundles its own OpenSSL via cffi.
# NOTE: On 32-bit Linux, cryptography has no manylinux_i686 wheel,
#       so pip will compile it from source. Rust (rustup) is required.
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

# Detect if we're on a native 32-bit system or cross-compiling from 64-bit
HOST_ARCH="$(uname -m)"

# ===============================
# System dependencies
# ===============================
# libffi-dev and zlib1g-dev are needed to compile cryptography from source on 32-bit.
# On 64-bit wheels exist and these aren't needed, but harmless to install.
install_deps() {
 echo "[+] Installing system dependencies"
 if command -v apt-get >/dev/null 2>&1; then
   sudo apt-get update
   sudo apt-get install -y python3 curl libffi-dev zlib1g-dev ca-certificates
   # Multilib tools needed if cross-compiling on a 64-bit host
   if [ "$HOST_ARCH" = "x86_64" ]; then
     sudo apt-get install -y gcc-multilib g++-multilib libc6-dev-i386 || true
   fi
 elif command -v dnf >/dev/null 2>&1; then
   sudo dnf install -y python3 curl libffi-devel zlib-devel ca-certificates
 elif command -v yum >/dev/null 2>&1; then
   sudo yum install -y python3 curl libffi-devel zlib-devel ca-certificates
 elif command -v pacman >/dev/null 2>&1; then
   sudo pacman -Sy --noconfirm python python-pip curl libffi zlib ca-certificates
 elif command -v apk >/dev/null 2>&1; then
   sudo apk add python3 py3-pip curl libffi-dev zlib-dev ca-certificates
 else
   echo "[!] No supported package manager found."
   echo "    Please install manually: python3 libffi-dev zlib1g-dev"
   echo "    (pip is NOT needed system-wide — the venv provides its own pip)"
   exit 1
 fi
}

install_deps

# ===============================
# Rust (needed to compile cryptography from source on 32-bit Linux)
# cryptography has NO pre-built manylinux_i686 wheel.
# ===============================
if ! command -v rustc >/dev/null 2>&1; then
 echo "[+] Installing Rust (required to build cryptography on 32-bit)"
 curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
 source "$HOME/.cargo/env"
fi

# Python SOABI reports 'i386' but Rust target is 'i686' — fix the mismatch
if [ "$HOST_ARCH" = "i686" ] || [ "$HOST_ARCH" = "i386" ]; then
 echo "[+] Setting Rust target to i686-unknown-linux-gnu"
 rustup target add i686-unknown-linux-gnu 2>/dev/null || true
 export CARGO_BUILD_TARGET=i686-unknown-linux-gnu
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
# pip + 32-bit requirements
# ===============================
echo "[+] Upgrading pip and installing 32-bit dependencies"
"$PIP" install --upgrade pip
"$PIP" install -r "$TESTING_DIR/requirements_32.txt"

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
echo "[✓] 32-bit Installation complete"
echo "    Python: $(python3 --version)"
echo "    cryptography: compiled from source (Rust)"
echo "================================================"

chmod +x "$APP_DIR/app.sh"
# "$APP_DIR/app.sh"
exec "$APP_DIR/app.sh"