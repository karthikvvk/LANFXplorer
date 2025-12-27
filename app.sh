#!/usr/bin/env bash
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"

OPENSSL_PREFIX="$APP_DIR/opt/openssl/openssl-standalone"
PY_PREFIX="$APP_DIR/lib/python-standalone"

export PATH="$PY_PREFIX/bin:$PATH"
export LD_LIBRARY_PATH="$OPENSSL_PREFIX/lib:$PY_PREFIX/lib:$LD_LIBRARY_PATH"
export PYTHONHOME="$PY_PREFIX"
export PYTHONPATH="$APP_DIR"

exec "$PY_PREFIX/bin/python3" "$APP_DIR/main.py"
