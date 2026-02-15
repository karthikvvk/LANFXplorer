#!/usr/bin/env bash
set -e

# =================================
# Terminal Detection & Re-launch
# If not running in a terminal (e.g., double-clicked from GUI),
# re-launch the script inside a terminal emulator
# =================================
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

# -------------------------------
# Load .env safely
# -------------------------------
if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

# ===============================
# Install build dependencies
# ===============================
DEPS="wget make gcc g++ curl tar"

install_deps() {
  echo "[+] Installing build dependencies: $DEPS"

  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y $DEPS
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y $DEPS
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y $DEPS
  elif command -v xbps-install >/dev/null 2>&1; then
    sudo xbps-install -Sy $DEPS
  elif command -v zypper >/dev/null 2>&1; then
    sudo zypper install -y $DEPS
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm $DEPS
  elif command -v apk >/dev/null 2>&1; then
    sudo apk add $DEPS
  elif command -v snap >/dev/null 2>&1; then
    for pkg in $DEPS; do
      sudo snap install "$pkg" 2>/dev/null || echo "[!] snap: $pkg not available, skipping"
    done
  elif command -v flatpak >/dev/null 2>&1; then
    echo "[!] flatpak cannot install system CLI tools ($DEPS)."
    echo "    Please install them manually with your system package manager."
    exit 1
  else
    echo "[!] No supported package manager found."
    echo "    Please install these PACKAGES manually: $DEPS"
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
fi

INSTALLER_FLAG="${INSTALLER:-false}"
INSTALLER_FLAG="$(echo "$INSTALLER_FLAG" | tr '[:upper:]' '[:lower:]')"

# -------------------------------
# If already installed → run app
# -------------------------------
if [ "$INSTALLER_FLAG" = "true" ]; then
  exec "$APP_DIR/app.sh"
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
# Build OpenSSL (standalone)
# ===============================
echo "[+] Building OpenSSL $OPENSSL_VERSION"

mkdir -p "$OPENSSL_SRC"
cd "$OPENSSL_SRC"

if [ ! -d "openssl-$OPENSSL_VERSION" ]; then
  wget https://www.openssl.org/source/openssl-$OPENSSL_VERSION.tar.gz
  tar -xzf openssl-$OPENSSL_VERSION.tar.gz
fi

cd "openssl-$OPENSSL_VERSION"

./Configure linux-x86_64 \
  --prefix="$OPENSSL_PREFIX" \
  --openssldir="$OPENSSL_PREFIX/ssl" \
  shared

make -j"$NPROC"
make install_sw

# ===============================
# Build Python 3.9.1 (standalone)
# ===============================
echo "[+] Building Python $PYTHON_VERSION"

mkdir -p "$PYTHON_SRC"
cd "$PYTHON_SRC"

if [ ! -d "Python-$PYTHON_VERSION" ]; then
  wget https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tgz
  tar -xzf Python-$PYTHON_VERSION.tgz
fi

cd "Python-$PYTHON_VERSION"

export CPPFLAGS="-I$OPENSSL_PREFIX/include"
export LDFLAGS="-L$OPENSSL_PREFIX/lib"
export LD_RUN_PATH="$OPENSSL_PREFIX/lib"
export PKG_CONFIG_PATH="$OPENSSL_PREFIX/lib/pkgconfig"

./configure \
  --prefix="$PY_PREFIX" \
  --with-openssl="$OPENSSL_PREFIX" \
  --enable-optimizations \
  --without-ensurepip

make -j"$NPROC"
make install

# ===============================
# pip + requirements
# ===============================
echo "[+] Installing pip + dependencies"

"$PY_PREFIX/bin/python3" -m ensurepip
"$PY_PREFIX/bin/python3" -m pip install --upgrade pip
"$PY_PREFIX/bin/python3" -m pip install -r "$APP_DIR/requirements.txt"

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

# ===============================
# Mark installation as complete
# ===============================
if grep -q "^INSTALLER=" "$ENV_FILE"; then
  sed -i "s/^INSTALLER=.*/INSTALLER='true'/" "$ENV_FILE"
else
  echo "INSTALLER='true'" >> "$ENV_FILE"
fi

echo "[✓] Installation complete"


chmod +x app.sh
./app.sh