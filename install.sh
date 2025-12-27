#!/usr/bin/env bash
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$APP_DIR/.env"

# -------------------------------
# Load .env safely
# -------------------------------
if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
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
PYTHON_VERSION="3.9.1"

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

echo "[✓] Installation complete"
