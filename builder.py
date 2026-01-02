#!/usr/bin/env python3

import os
import shutil
import tarfile
import zipfile
import platform
import datetime

ROOT = os.getcwd()
APPBUILD = os.path.join(ROOT, "appbuild")
SYSTEM = platform.system().lower()
date = datetime.datetime.now().strftime("%Y-%m-%d")
# Detect OS and build accordingly
try:
    os.system("flutter")
    if SYSTEM.startswith("win"):
        print("[*] Building for Windows...")
        os.system("flutter clean && flutter pub get && flutter build windows --release")
    else:
        print("[*] Building for Linux...")
        os.system("flutter clean && flutter pub get && flutter build linux --release")
except:
    print("flutter not found")
# Files and directories to include
ITEMS = [
    "analysis_options.yaml",
    "pki",
    "api_bridge.py",
    "pubspec.lock",
    "app.sh",
    "app.bat",  # Windows launcher
    "pubspec.yaml",
    "receiver_api_functions.py",
    "config_manager.py",
    "recive.py",
    "devtools_options.yaml",
    "requirements.txt",
    "files.iml",
    "scanner.py",
    "host_selecter.py",
    "scripts",
    "installer.py",
    "sender_api_functions.py",
    "install.sh",
    "install.bat",  # Windows installer
    "send.py",
    "lanfxplorery.png",
    "startsetup.py",
    "main.py",
    "wifi_speed.py",
    "path_security.py",
]

# Set Flutter bundle source and executable name based on OS
if SYSTEM.startswith("win"):
    FLUTTER_BUNDLE_SRC = "\\build\\windows\\runner\\Release"
    EXECUTABLE_NAME = "lanfxplorer.exe"
else:
    FLUTTER_BUNDLE_SRC = "/build/linux/x64/release/bundle"
    EXECUTABLE_NAME = "lanfxplorer"


def get_version_from_pubspec():
    with open("pubspec.yaml", "r") as f:
        for line in f:
            if line.strip().startswith("version:"):
                return line.split(":", 1)[1].strip()
    raise RuntimeError("version not found in pubspec.yaml")


def main():
    # Fresh appbuild
    if os.path.exists(APPBUILD):
        shutil.rmtree(APPBUILD)
    os.makedirs(APPBUILD)

    # Copy listed items
    for item in ITEMS:
        src = os.path.join(ROOT, item)
        dst = os.path.join(APPBUILD, item)

        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    # Copy flutter bundle - maintain full directory structure
    bundle_dest = os.path.join(APPBUILD, "build", "linux", "x64", "release", "bundle")
    shutil.copytree(
        ROOT + FLUTTER_BUNDLE_SRC,
        bundle_dest,
        dirs_exist_ok=True,
    )

    # Copy built executable to root directory for easy trial runs
    executable_src = os.path.join(ROOT + FLUTTER_BUNDLE_SRC, EXECUTABLE_NAME)
    executable_dst = os.path.join(ROOT, EXECUTABLE_NAME)
    if os.path.exists(executable_src):
        shutil.copy2(executable_src, executable_dst)
        print(f"[*] Copied {EXECUTABLE_NAME} to root directory for easy testing")
    else:
        print(f"[!] Warning: Executable not found at {executable_src}")

    # Read version
    version = get_version_from_pubspec()
    
    # Create archive based on OS
    if SYSTEM.startswith("win"):
        # Create zip for Windows
        archive_name = f"{SYSTEM}_{date}_{version}.zip"
        with zipfile.ZipFile(archive_name, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(APPBUILD):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.join("appbuild", os.path.relpath(file_path, APPBUILD))
                    zipf.write(file_path, arcname)
        print(f"[*] Created archive: {archive_name}")
    else:
        # Create tar.gz for Linux
        archive_name = f"{SYSTEM}_{date}_{version}.tar.gz"
        with tarfile.open(archive_name, "w:gz") as tar:
            tar.add(APPBUILD, arcname="appbuild")
        print(f"[*] Created archive: {archive_name}")


if __name__ == "__main__":
    main()
