#!/usr/bin/env python3
"""
LANFXplorer — CLI Profile Creation (Headless / 32-bit)

Replicates the Flutter login page flow in the terminal.
Prompts for username, password, and output directory if no
existing profile is found (i.e. no password in keyring/env).
"""

import os
import sys
import getpass
from pathlib import Path

# Ensure project root is on sys.path
APP_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(APP_DIR))

from config_manager import get_config_manager
from path_security import get_lanfxplorer_root, validate_path_access, ensure_lanfxplorer_directory


def _prompt_username() -> str:
    """Prompt for username with sensible default."""
    default = os.environ.get("USER", getpass.getuser())
    while True:
        name = input(f"  Username [{default}]: ").strip()
        if not name:
            name = default
        if name:
            return name
        print("  [!] Username cannot be empty.")


def _prompt_password() -> str:
    """Prompt for password (hidden) with confirmation, min 4 chars."""
    while True:
        pwd = getpass.getpass("  Password (min 4 chars): ")
        if len(pwd) < 4:
            print("  [!] Password must be at least 4 characters.")
            continue
        confirm = getpass.getpass("  Confirm password: ")
        if pwd != confirm:
            print("  [!] Passwords do not match. Try again.")
            continue
        return pwd


def _prompt_outdir() -> str:
    """Prompt for output directory, validated against path_security."""
    default = get_lanfxplorer_root()
    while True:
        path = input(f"  Output directory [{default}]: ").strip()
        if not path:
            path = default
        # Expand ~ and resolve
        path = str(Path(path).expanduser().resolve())
        is_valid, _ = validate_path_access(path)
        if is_valid:
            os.makedirs(path, exist_ok=True)
            return path
        print(f"  [!] Directory must be within {default}")


def ensure_profile() -> bool:
    """
    Check if a profile exists. If not, run interactive CLI prompts.
    
    Returns True if a valid profile is ready, False if user cancelled.
    """
    config_mgr = get_config_manager()

    # Check for existing profile
    if config_mgr.has_password():
        print("[✓] Existing profile found — skipping login")
        return True

    # No profile — interactive creation
    print("")
    print("================================================")
    print("  LANFXplorer — Profile Setup")
    print("================================================")
    print("  No profile found. Please create one to continue.")
    print("")

    try:
        username = _prompt_username()
        password = _prompt_password()
        outdir = _prompt_outdir()
    except (KeyboardInterrupt, EOFError):
        print("\n  [!] Profile creation cancelled.")
        return False

    # --- Write to .env (same logic as Flutter login_page.dart) ---
    env_file = APP_DIR / ".env"
    env_content = ""
    if env_file.exists():
        env_content = env_file.read_text()

    lines = env_content.split("\n")
    new_lines = []
    found_user = found_outdir = found_srcdir = False

    for line in lines:
        if line.startswith("USER="):
            new_lines.append(f"USER={username}")
            found_user = True
        elif line.startswith("OUTDIR="):
            new_lines.append(f"OUTDIR={outdir}")
            found_outdir = True
        elif line.startswith("SRCDIR="):
            new_lines.append(f"SRCDIR={outdir}")
            found_srcdir = True
        else:
            new_lines.append(line)

    if not found_user:
        new_lines.append(f"USER={username}")
    if not found_outdir:
        new_lines.append(f"OUTDIR={outdir}")
    if not found_srcdir:
        new_lines.append(f"SRCDIR={outdir}")

    env_file.write_text("\n".join(new_lines))

    # Store password in keyring (same as /set_password endpoint)
    config_mgr.set_password(password)

    # Also set env vars for the current session
    os.environ["USER"] = username
    os.environ["PASSWORD"] = password
    os.environ["OUTDIR"] = outdir
    os.environ["SRCDIR"] = outdir

    print("")
    print(f"  [✓] Profile created")
    print(f"      Username : {username}")
    print(f"      Password : (set)")
    print(f"      Output   : {outdir}")
    print("================================================")
    print("")
    return True


if __name__ == "__main__":
    # Allow standalone testing
    result = ensure_profile()
    sys.exit(0 if result else 1)
