"""
Architecture detection module for LANFXplorer.

Detects system architecture (32-bit vs 64-bit) and provides
version constants for Python, OpenSSL, and download URLs.

Usage (from main project):
    from arch_config import ARCH, PY_VERSION, SSL_TARGET, PY_EMBED_URL
"""

import platform
import struct
import sys
import os


def detect_arch():
    """Detect if running on 32-bit or 64-bit system."""
    bits = struct.calcsize("P") * 8  # pointer size in bits
    return bits


def is_32bit():
    """Return True if running on a 32-bit Python interpreter."""
    return detect_arch() == 32


# ─── Architecture ────────────────────────────────────────
BITS = detect_arch()
IS_32BIT = is_32bit()
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
MACHINE = platform.machine().lower()  # e.g. x86_64, i686, AMD64, x86

# Friendly arch label
if IS_32BIT:
    ARCH = "win32" if IS_WINDOWS else "i686"
else:
    ARCH = "amd64" if IS_WINDOWS else "x86_64"


# ─── Python Versions ────────────────────────────────────
PY_VERSION_32 = "3.10.11"
PY_VERSION_64 = "3.12.8"
PY_VERSION = PY_VERSION_32 if IS_32BIT else PY_VERSION_64


# ─── OpenSSL ─────────────────────────────────────────────
OPENSSL_VERSION = "3.2.1"

# Linux: ./Configure target
SSL_TARGET_32 = "linux-x86"
SSL_TARGET_64 = "linux-x86_64"
SSL_TARGET = SSL_TARGET_32 if IS_32BIT else SSL_TARGET_64

OPENSSL_SRC_URL = (
    f"https://www.openssl.org/source/openssl-{OPENSSL_VERSION}.tar.gz"
)

# Windows: slproweb installer
SSL_WIN_32 = "Win32OpenSSL_Light-3_5_5.exe"
SSL_WIN_64 = "Win64OpenSSL_Light-3_5_5.exe"
SSL_WIN_INSTALLER = SSL_WIN_32 if IS_32BIT else SSL_WIN_64
SSL_WIN_INSTALL_DIR_32 = r"C:\Program Files (x86)\OpenSSL-Win32"
SSL_WIN_INSTALL_DIR_64 = r"C:\Program Files\OpenSSL-Win64"
SSL_WIN_INSTALL_DIR = SSL_WIN_INSTALL_DIR_32 if IS_32BIT else SSL_WIN_INSTALL_DIR_64


# ─── Python Embeddable (Windows) ────────────────────────
PY_EMBED_BASE = "https://www.python.org/ftp/python"
PY_EMBED_URL_32 = f"{PY_EMBED_BASE}/{PY_VERSION_32}/python-{PY_VERSION_32}-embed-win32.zip"
PY_EMBED_URL_64 = f"{PY_EMBED_BASE}/{PY_VERSION_64}/python-{PY_VERSION_64}-embed-amd64.zip"
PY_EMBED_URL = PY_EMBED_URL_32 if IS_32BIT else PY_EMBED_URL_64

# Python source (Linux)
PY_SRC_URL_32 = f"{PY_EMBED_BASE}/{PY_VERSION_32}/Python-{PY_VERSION_32}.tgz"
PY_SRC_URL_64 = f"{PY_EMBED_BASE}/{PY_VERSION_64}/Python-{PY_VERSION_64}.tgz"
PY_SRC_URL = PY_SRC_URL_32 if IS_32BIT else PY_SRC_URL_64


# ─── Requirements File ──────────────────────────────────
REQUIREMENTS_FILE = "requirements_32.txt" if IS_32BIT else "requirements_64.txt"


# ─── Extra build deps for 32-bit Linux ──────────────────
LINUX_32BIT_EXTRA_DEPS = ["gcc-multilib", "g++-multilib", "libc6-dev-i386"]


def summary():
    """Print a summary of detected architecture settings."""
    lines = [
        f"Architecture   : {ARCH} ({BITS}-bit)",
        f"Platform       : {'Windows' if IS_WINDOWS else 'Linux' if IS_LINUX else sys.platform}",
        f"Machine        : {MACHINE}",
        f"Python version : {PY_VERSION}",
        f"OpenSSL target : {SSL_TARGET if IS_LINUX else SSL_WIN_INSTALLER}",
        f"Requirements   : {REQUIREMENTS_FILE}",
    ]
    if IS_WINDOWS:
        lines.append(f"Python embed   : {PY_EMBED_URL}")
        lines.append(f"OpenSSL dir    : {SSL_WIN_INSTALL_DIR}")
    else:
        lines.append(f"Python src     : {PY_SRC_URL}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
