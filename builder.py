#!/usr/bin/env python3

import os
import shutil
import tarfile

ROOT = os.getcwd()
APPBUILD = os.path.join(ROOT, "appbuild")
# os.system("flutter clean && flutter pub get && flutter build linux --release")
# Files and directories to include
ITEMS = [
    "analysis_options.yaml",
    "pki",
    "api_bridge.py",
    "pubspec.lock",
    "app.sh",
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
    "send.py",
    "lanfxplorery.png",
    "startsetup.py",
    "main.py",
    "wifi_speed.py",
    "path_security.py",
]

FLUTTER_BUNDLE_SRC = "/build/linux/x64/release/bundle"


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

    # Copy flutter bundle
    shutil.copytree(
        ROOT + FLUTTER_BUNDLE_SRC,
        os.path.join(APPBUILD, "bundle"),
        dirs_exist_ok=True,
    )

    # Read version
    version = get_version_from_pubspec()
    archive_name = f"{version}.tar.gz"

    # Create tar.gz
    with tarfile.open(archive_name, "w:gz") as tar:
        tar.add(APPBUILD, arcname="appbuild")

    print(f"Created archive: {archive_name}")


if __name__ == "__main__":
    main()
