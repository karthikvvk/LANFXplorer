#!/usr/bin/env python3
"""
Show Config - Diagnostic utility
Prints current environment configuration and password status.
"""
import os
import sys
from pathlib import Path

# Setup path
APP_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(APP_DIR))

from config_manager import get_config_manager
from path_security import get_lanfxplorer_root
from app_config import get_config

def main():
    print("="*40)
    print("  LANFXplorer Configuration Check")
    print("="*40)
    
    # 1. Check Password
    cm = get_config_manager()
    pwd = cm.get_password()
    
    print(f"\n[Password Status]")
    if pwd:
        print(f"  ✓ Password is SET in {cm._system} keyring/env")
        print(f"  Value: '{pwd}'") # Showing explicitly for debugging
    else:
        print(f"  ✗ Password is NOT SET (auth will fail)")
        
    # 2. Check .env Config
    print(f"\n[.env Configuration]")
    config = get_config()
    env_vars = config.get_all()
    
    for key in ["host", "port", "out_dir", "user", "lanfxplorer_headless"]:
        val = env_vars.get(key) or os.environ.get(key.upper())
        print(f"  {key.upper()}: {val}")
        
    # 3. Path Security
    print(f"\n[Path Security]")
    root = get_lanfxplorer_root()
    print(f"  Root: {root}")
    print(f"  Exists: {os.path.exists(root)}")

if __name__ == "__main__":
    main()
