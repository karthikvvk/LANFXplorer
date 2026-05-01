#!/usr/bin/env bash
set -e

# =================================
# LANFXplorer — Linux 32-bit (i686) Installer
# Builds standalone Python + OpenSSL from source to avoid
# 32-bit wheel issues with cryptography/bcrypt on i686.
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

# Guard: autoconf/make cannot handle spaces in paths
case "$APP_DIR" in
  *" "*)
    echo "[✗] ERROR: Installation path contains spaces:"
    echo "    $APP_DIR"
    echo ""
    echo "    Autoconf/make build systems do not support spaces in paths."
    echo "    Please move/extract LANFXplorer to a path without spaces, e.g.:"
    echo "    /home/$(whoami)/LANFXplorer"
    exit 1
    ;;
esac

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
  exec "$APP_DIR/32bitcodes/app_32bit.sh"
fi

# ===============================
# Install build dependencies
# ===============================
DEPS="wget make gcc g++ curl tar"

install_deps() {
  echo "[+] Installing build dependencies: $DEPS + dev libraries + tkinter (dev)"

  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y $DEPS perl libffi-dev zlib1g-dev gnome-keyring libsecret-1-0 libsecret-1-dev python3-tk tk-dev
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y $DEPS perl libffi-devel zlib-devel gnome-keyring libsecret libsecret-devel python3-tkinter tk-devel
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y $DEPS perl libffi-devel zlib-devel gnome-keyring libsecret libsecret-devel python3-tkinter tk-devel
  elif command -v xbps-install >/dev/null 2>&1; then
    sudo xbps-install -Sy $DEPS perl libffi-devel zlib-devel gnome-keyring libsecret libsecret-devel python3-tkinter tk
  elif command -v zypper >/dev/null 2>&1; then
    sudo zypper install -y $DEPS perl libffi-devel zlib-devel gnome-keyring libsecret-devel python3-tk tk-devel
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm $DEPS perl libffi zlib gnome-keyring libsecret python-tkinter tk
  elif command -v apk >/dev/null 2>&1; then
    sudo apk add $DEPS perl libffi-dev zlib-dev gnome-keyring libsecret-dev python3-tkinter tk-dev
  else
    echo "[!] No supported package manager found."
    echo "    Please install these PACKAGES manually: $DEPS perl libffi-dev zlib1g-dev gnome-keyring libsecret python3-tk"
    exit 1
  fi
}

# Only install if any dependency is missing
MISSING=""
for dep in $DEPS; do
  if ! command -v "$dep" >/dev/null 2>&1; then
    MISSING="$MISSING $dep"
  fi
done

if [ -n "$MISSING" ]; then
  echo "[!] Missing dependencies:$MISSING"
  install_deps
else
  echo "[✓] All build dependencies already present"
  # Still ensure tkinter dev package is present (dev dependency)
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get install -y python3-tk tk-dev 2>/dev/null || true
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3-tkinter tk-devel 2>/dev/null || true
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --noconfirm python-tkinter tk 2>/dev/null || true
  fi
fi

OPENSSL_VERSION="3.2.1"
PYTHON_VERSION="3.12.8"

OPT_DIR="$APP_DIR/opt"
OPENSSL_SRC="$OPT_DIR/openssl-src"
OPENSSL_PREFIX="$OPT_DIR/openssl"

PYTHON_SRC="$OPT_DIR/python-src"
PY_PREFIX="$OPT_DIR/python39"

NPROC="$(nproc || echo 1)"

mkdir -p "$OPT_DIR"

# ===============================
# Architecture detection
# ===============================
HOST_ARCH="$(uname -m)"
if [ "$HOST_ARCH" = "i686" ] || [ "$HOST_ARCH" = "i386" ]; then
  ARCH_BITS=32
  OPENSSL_TARGET="linux-x86"
else
  ARCH_BITS=64
  OPENSSL_TARGET="linux-x86_64"
fi
echo "[+] Detected architecture: ${HOST_ARCH} (${ARCH_BITS}-bit)"

# ===============================
# Build OpenSSL (standalone)
# ===============================
if [ -d "$OPENSSL_PREFIX/lib" ] || [ -d "$OPENSSL_PREFIX/lib64" ]; then
  echo "[✓] OpenSSL already built at: $OPENSSL_PREFIX"
else
  echo "[+] Building OpenSSL $OPENSSL_VERSION"

  mkdir -p "$OPENSSL_SRC"
  cd "$OPENSSL_SRC"

  if [ ! -d "openssl-$OPENSSL_VERSION" ]; then
    wget https://www.openssl.org/source/openssl-$OPENSSL_VERSION.tar.gz
    tar -xzf openssl-$OPENSSL_VERSION.tar.gz
  fi

  cd "openssl-$OPENSSL_VERSION"

  ./Configure $OPENSSL_TARGET \
    --prefix="$OPENSSL_PREFIX" \
    --openssldir="$OPENSSL_PREFIX/ssl" \
    shared

  make -j"$NPROC"
  make install_sw
fi

# Detect lib vs lib64 for OpenSSL
if [ -d "$OPENSSL_PREFIX/lib64" ] && [ ! -d "$OPENSSL_PREFIX/lib" ]; then
  OPENSSL_LIB="$OPENSSL_PREFIX/lib64"
else
  OPENSSL_LIB="$OPENSSL_PREFIX/lib"
fi
echo "[✓] OpenSSL libraries at: $OPENSSL_LIB"

# ===============================
# Build Python (standalone)
# ===============================
if [ -x "$PY_PREFIX/bin/python3" ]; then
  echo "[✓] Python already built at: $PY_PREFIX"
else
  echo "[+] Building Python $PYTHON_VERSION"

  mkdir -p "$PYTHON_SRC"
  cd "$PYTHON_SRC"

  if [ ! -d "Python-$PYTHON_VERSION" ]; then
    wget https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tgz
    tar -xzf Python-$PYTHON_VERSION.tgz
  fi

  cd "Python-$PYTHON_VERSION"

  export CPPFLAGS="-I$OPENSSL_PREFIX/include"
  export LDFLAGS="-L$OPENSSL_LIB"
  export LD_RUN_PATH="$OPENSSL_LIB"
  export PKG_CONFIG_PATH="$OPENSSL_LIB/pkgconfig"

  ./configure \
    --prefix="$PY_PREFIX" \
    --with-openssl="$OPENSSL_PREFIX" \
    --enable-optimizations \
    --with-tcltk-includes="$(pkg-config --cflags tk 2>/dev/null || echo '')" \
    --with-tcltk-libs="$(pkg-config --libs tk 2>/dev/null || echo '')" \
    --without-ensurepip

  make -j"$NPROC"
  make install
fi

# Verify SSL module compiled
echo "[+] Verifying SSL module..."
export LD_LIBRARY_PATH="$OPENSSL_LIB:$LD_LIBRARY_PATH"
"$PY_PREFIX/bin/python3" -c "import ssl; print('[✓] SSL module OK: ' + ssl.OPENSSL_VERSION)" || {
  echo "[✗] FATAL: Python _ssl module failed to build."
  echo "    OpenSSL headers/libs were not found during Python compilation."
  echo "    Check that OpenSSL built correctly at: $OPENSSL_PREFIX"
  exit 1
}

# ===============================
# pip + requirements
# ===============================
echo "[+] Installing pip + dependencies"

"$PY_PREFIX/bin/python3" -m ensurepip
"$PY_PREFIX/bin/python3" -m pip install --upgrade pip
"$PY_PREFIX/bin/python3" -m pip install -r "$TESTING_DIR/requirements_32.txt"

# Install dev requirements if present (optional developer extras)
if [ -f "$APP_DIR/dev_requirements.txt" ]; then
  echo "[+] dev_requirements.txt found — installing dev extras"
  "$PY_PREFIX/bin/python3" -m pip install -r "$APP_DIR/dev_requirements.txt"
else
  echo "[i] No dev_requirements.txt found — skipping dev extras"
fi

echo "[✓] Dependencies installed"

# ===============================
# Firewall rules
# ===============================
echo "[+] Configuring firewall rules for LANFXplorer..."
"$PY_PREFIX/bin/python3" "$APP_DIR/firewall_manager.py" --install || {
  echo "[!] Firewall configuration failed (non-fatal). You may need to manually allow ports."
}

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
Version=1.1
Type=Application
Name=LANFXplorer
GenericName=LAN File Transfer
Comment=High-speed P2P LAN file transfer over QUIC.
Exec=$APP_DIR/32bitcodes/app_32bit.sh
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

# Mark install complete
if grep -q "^INSTALLER=" "$ENV_FILE" 2>/dev/null; then
  sed -i "s/^INSTALLER=.*/INSTALLER='true'/" "$ENV_FILE"
else
  echo "INSTALLER='true'" >> "$ENV_FILE"
fi

echo ""
echo "================================================"
echo "[✓] 32-bit Installation complete"
echo "    Python: $($PY_PREFIX/bin/python3 --version)"
echo "    OpenSSL: $($OPENSSL_PREFIX/bin/openssl version 2>/dev/null || echo built)"
echo "    SSL linked against: $OPENSSL_LIB"
echo "================================================"

chmod +x "$APP_DIR/32bitcodes/app_32bit.sh"
exec "$APP_DIR/32bitcodes/app_32bit.sh"