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

# Normalize installer flag
INSTALLER_FLAG="${INSTALLER:-false}"
INSTALLER_FLAG="$(echo "$INSTALLER_FLAG" | tr '[:upper:]' '[:lower:]')"

# -------------------------------
# If already installed → run app
# -------------------------------
if [ "$INSTALLER_FLAG" = "true" ]; then
  # echo "[✓] Installer flag true — launching app"
  exec "$APP_DIR/app.sh"
fi

APP_DIR="$(cd "$(dirname "$0")" && pwd)"

OPENSSL_VERSION="3.2.1"
PYTHON_VERSION="3.12.2"

OPT_DIR="$APP_DIR/opt/openssl"
LIB_DIR="$APP_DIR/lib"

OPENSSL_PREFIX="$OPT_DIR/openssl-standalone"
PY_PREFIX="$LIB_DIR/python-standalone"

NPROC="$(nproc)"

echo "[+] Installing OpenSSL"

mkdir -p "$OPT_DIR"
cd "$OPT_DIR"

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
make install

echo "[+] Installing Python"

mkdir -p "$LIB_DIR"
cd "$LIB_DIR"

if [ ! -d "Python-$PYTHON_VERSION" ]; then
  wget https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tgz
  tar -xzf Python-$PYTHON_VERSION.tgz
fi

cd "Python-$PYTHON_VERSION"

export CPPFLAGS="-I$OPENSSL_PREFIX/include"
export LDFLAGS="-L$OPENSSL_PREFIX/lib"
export LD_RUN_PATH="$OPENSSL_PREFIX/lib"

./configure \
  --prefix="$PY_PREFIX" \
  --with-openssl="$OPENSSL_PREFIX" \
  --enable-optimizations \
  --without-ensurepip

make -j"$NPROC"
make install

echo "[+] Installing pip + requirements"

"$PY_PREFIX/bin/python3" -m ensurepip
"$PY_PREFIX/bin/python3" -m pip install --upgrade pip
"$PY_PREFIX/bin/python3" -m pip install -r "$APP_DIR/requirements.txt"

echo "[+] Creating runtime directories"
mkdir -p "$APP_DIR/data" "$APP_DIR/logs"

echo "[+] Creating desktop entry"

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
