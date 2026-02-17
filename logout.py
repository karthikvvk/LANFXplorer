#!/usr/bin/env python3
"""
LANFXplorer — Logout / Cleanup Orchestrator

Stops all running LANFXplorer services and resets the environment.
Reuses existing modules:
  - main.cleanup_existing_services()  →  kill processes on ports 4433-4437, 5000
  - reset_env.reset_environment()     →  clear keyring, delete certs, reset .env

Usage:
    python3 logout.py          # from project root
    # or via the 32-bit launcher's Python:
    /path/to/opt/python39/bin/python3 logout.py
"""

import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
APP_DIR = Path(__file__).parent.resolve()
os.chdir(APP_DIR)
sys.path.insert(0, str(APP_DIR))


def main():
    print("")
    print("================================================")
    print("  LANFXplorer — Logout")
    print("================================================")

    # Step 1: Stop running services
    print("[→] Stopping running services...")
    try:
        from main import cleanup_existing_services
        cleanup_existing_services()
        print("[✓] Services stopped")
    except Exception as e:
        print(f"[⚠] Could not stop services: {e}")

    # Step 2: Reset environment (keyring, certs, .env)
    print("[→] Resetting environment...")
    try:
        from reset_env import reset_environment
        reset_environment()
        print("[✓] Environment reset complete")
    except Exception as e:
        print(f"[✗] Environment reset failed: {e}")
        return 1

    print("")
    print("================================================")
    print("  Logged out successfully.")
    print("  Run app.sh or app_32bit.sh to start fresh.")
    print("================================================")
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
