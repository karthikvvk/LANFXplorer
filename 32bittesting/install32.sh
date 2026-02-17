 #!/usr/bin/env bash
set -e


# =================================
# LANFXplorer — Linux 32-bit (i686) Installer
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
   echo "    Please move/extract LANFXplorer to a path without spaces."
   exit 1
   ;;
esac


# Load .env
if [ -f "$ENV_FILE" ]; then
 set -a
 source "$ENV_FILE"
 set +a
fi


# ===============================
# 32-bit specific versions
# ===============================
OPENSSL_VERSION="3.2.1"
PYTHON_VERSION="3.10.11"
SSL_TARGET="linux-x86"


OPT_DIR="$APP_DIR/opt"
OPENSSL_SRC="$OPT_DIR/openssl-src"
OPENSSL_PREFIX="$OPT_DIR/openssl"


PYTHON_SRC="$OPT_DIR/python-src"
PY_PREFIX="$OPT_DIR/python39"


NPROC="$(nproc || echo 1)"


mkdir -p "$OPT_DIR"


# ===============================
# Install build dependencies (32-bit specific)
# ===============================
DEPS="wget make gcc g++ curl tar"


# Detect if we're on a native 32-bit system or cross-compiling from 64-bit
HOST_ARCH="$(uname -m)"
if [ "$HOST_ARCH" = "x86_64" ]; then
 # Cross-compiling on 64-bit host — need multilib packages
 DEPS_32="gcc-multilib g++-multilib libc6-dev-i386"
else
 # Native 32-bit system (i686/i386) — no multilib needed
 DEPS_32=""
fi


# Dev libraries required for Python compilation (not detectable via command -v)
DEV_LIBS_INSTALLED=false


install_dev_libs() {
 echo "[+] Installing dev libraries: zlib, libffi, ca-certificates"


 if command -v apt-get >/dev/null 2>&1; then
   sudo apt-get update
   sudo apt-get install -y perl libffi-dev zlib1g-dev ca-certificates $DEPS_32
 elif command -v dnf >/dev/null 2>&1; then
   sudo dnf install -y perl libffi-devel zlib-devel ca-certificates
 elif command -v yum >/dev/null 2>&1; then
   sudo yum install -y perl libffi-devel zlib-devel ca-certificates
 elif command -v pacman >/dev/null 2>&1; then
   sudo pacman -Sy --noconfirm perl libffi zlib ca-certificates
 elif command -v apk >/dev/null 2>&1; then
   sudo apk add perl libffi-dev zlib-dev ca-certificates
 else
   echo "[!] No supported package manager found."
   echo "    Please install manually: perl libffi-dev zlib1g-dev ca-certificates"
   exit 1
 fi
 DEV_LIBS_INSTALLED=true
}


install_cli_tools() {
 echo "[+] Installing CLI build tools: $DEPS"


 if command -v apt-get >/dev/null 2>&1; then
   $DEV_LIBS_INSTALLED || sudo apt-get update
   sudo apt-get install -y $DEPS
 elif command -v dnf >/dev/null 2>&1; then
   sudo dnf install -y $DEPS
 elif command -v yum >/dev/null 2>&1; then
   sudo yum install -y $DEPS
 elif command -v pacman >/dev/null 2>&1; then
   sudo pacman -Sy --noconfirm $DEPS
 elif command -v apk >/dev/null 2>&1; then
   sudo apk add $DEPS
 else
   echo "[!] No supported package manager found."
   echo "    Please install manually: $DEPS"
   exit 1
 fi
}


# Wrapper: try wget normally, fall back to --no-check-certificate
safe_wget() {
 local url="$1"
 wget "$url" 2>/dev/null && return 0
 echo "[!] wget failed (certificate issue?), retrying with --no-check-certificate"
 wget --no-check-certificate "$url"
}


# ALWAYS install dev libraries (they are headers, not CLI tools — can't detect via command -v)
install_dev_libs


# Check CLI tools
MISSING=""
for dep in $DEPS; do
 if ! command -v "$dep" >/dev/null 2>&1; then
   MISSING="$MISSING $dep"
 fi
done


if [ -n "$MISSING" ]; then
 echo "[!] Missing CLI tools:$MISSING"
 install_cli_tools
else
 echo "[✓] All CLI build tools already present"
fi


# If already installed → run app
INSTALLER_FLAG="${INSTALLER:-false}"
INSTALLER_FLAG="$(echo "$INSTALLER_FLAG" | tr '[:upper:]' '[:lower:]')"


if [ "$INSTALLER_FLAG" = "true" ]; then
 exec "$APP_DIR/app.sh"
fi


# ===============================
# Build OpenSSL (32-bit)
# ===============================
echo "[+] Building OpenSSL $OPENSSL_VERSION (32-bit: $SSL_TARGET)"


mkdir -p "$OPENSSL_SRC"
cd "$OPENSSL_SRC"


if [ ! -d "openssl-$OPENSSL_VERSION" ]; then
 safe_wget https://www.openssl.org/source/openssl-$OPENSSL_VERSION.tar.gz
 tar -xzf openssl-$OPENSSL_VERSION.tar.gz
fi


cd "openssl-$OPENSSL_VERSION"


./Configure "$SSL_TARGET" \
 --prefix="$OPENSSL_PREFIX" \
 --openssldir="$OPENSSL_PREFIX/ssl" \
 shared


make -j"$NPROC"
make install_sw


# Detect lib vs lib64
if [ -d "$OPENSSL_PREFIX/lib64" ] && [ ! -d "$OPENSSL_PREFIX/lib" ]; then
 OPENSSL_LIB="$OPENSSL_PREFIX/lib64"
else
 OPENSSL_LIB="$OPENSSL_PREFIX/lib"
fi
echo "[✓] OpenSSL libraries at: $OPENSSL_LIB"


# ===============================
# Build Python (32-bit)
# ===============================
echo "[+] Building Python $PYTHON_VERSION (32-bit)"


mkdir -p "$PYTHON_SRC"
cd "$PYTHON_SRC"


if [ ! -d "Python-$PYTHON_VERSION" ]; then
 safe_wget https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tgz
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
 --without-ensurepip


make -j"$NPROC"
make install


# Verify SSL module
echo "[+] Verifying SSL module..."
export LD_LIBRARY_PATH="$OPENSSL_LIB:$LD_LIBRARY_PATH"
"$PY_PREFIX/bin/python3" -c "import ssl; print('[✓] SSL module OK: ' + ssl.OPENSSL_VERSION)" || {
 echo "[✗] FATAL: Python _ssl module failed to build."
 echo "    OpenSSL headers/libs were not found during Python compilation."
 echo "    Check that OpenSSL built correctly at: $OPENSSL_PREFIX"
 exit 1
}


# ===============================
# pip + 32-bit requirements
# ===============================
echo "[+] Installing pip + 32-bit dependencies"


"$PY_PREFIX/bin/python3" -m ensurepip
"$PY_PREFIX/bin/python3" -m pip install --upgrade pip


# ===============================
# Rust (needed to compile cryptography from source on 32-bit Linux)
# cryptography has NO pre-built manylinux_i686 wheel
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


# Point Rust's openssl-sys crate to our custom-built OpenSSL
export OPENSSL_DIR="$OPENSSL_PREFIX"
export OPENSSL_LIB_DIR="$OPENSSL_LIB"
export OPENSSL_INCLUDE_DIR="$OPENSSL_PREFIX/include"


"$PY_PREFIX/bin/python3" -m pip install -r "$TESTING_DIR/requirements_32.txt"


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
if grep -q "^INSTALLER=" "$ENV_FILE"; then
 sed -i "s/^INSTALLER=.*/INSTALLER='true'/" "$ENV_FILE"
else
 echo "INSTALLER='true'" >> "$ENV_FILE"
fi


echo ""
echo "================================================"
echo "[✓] 32-bit Installation complete"
echo "    Python: $PYTHON_VERSION (32-bit)"
echo "    OpenSSL: $OPENSSL_VERSION ($SSL_TARGET)"
echo "================================================"


chmod +x "$APP_DIR/app.sh"
"$APP_DIR/app.sh"



