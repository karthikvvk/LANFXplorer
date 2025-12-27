#!/usr/bin/env python3
"""
LANFXplorer Main Entry Point

Orchestrates the complete application startup in order:
1. startsetup.py - PKI and environment setup
2. recive.py - QUIC receiver (background)
3. api_bridge.py - Flask API (background)
4. lanfxplorer.AppImage / lanfxplorer.exe - UI
"""
import os
import sys
import subprocess
import time
import platform
from pathlib import Path

from startsetup import write_env

APP_DIR = Path(__file__).parent.resolve()
os.chdir(APP_DIR)
sys.path.insert(0, str(APP_DIR))


def print_status(status: str, message: str):
    symbols = {"ok": "✓", "fail": "✗", "info": "ℹ", "warn": "⚠", "run": "→"}
    print(f"[{symbols.get(status, '•')}] {message}")


def run_script(script_name: str, wait: bool = True):
    script_path = APP_DIR / script_name
    if not script_path.exists():
        print_status("fail", f"Script not found: {script_path}")
        return None

    print_status("run", f"Starting {script_name}")
    proc = subprocess.Popen(
        [sys.executable, str(script_path)],
        cwd=str(APP_DIR),
        stdout=None if not wait else subprocess.PIPE,
        stderr=None if not wait else subprocess.PIPE,
    )

    if wait:
        proc.wait()
    else:
        time.sleep(1)
        if proc.poll() is not None:
            return None

    return proc


def run_ui():

    ui_path = APP_DIR / "bundle" / "lanfxplorer"
    if not ui_path.exists():
        print_status("fail", f"UI executable not found: {ui_path}")
        return None
    print_status("run", "Starting LANFXplorer UI")
    return subprocess.Popen([str(ui_path)], cwd=str(APP_DIR))


def main():
    processes = []
    # try:
    run_script("startsetup.py", wait=True)

    receiver = run_script("recive.py", wait=False)
    if not receiver:
        return
    processes.append(("Receiver", receiver))

    time.sleep(5)

    api = run_script("api_bridge.py", wait=False)
    if api:
        processes.append(("API Bridge", api))

    time.sleep(2)

    ui_proc = run_ui()
    if not ui_proc:
        return
    processes.append(("UI", ui_proc))

    ui_proc.wait()

    # except KeyboardInterrupt:
    #     print_status("info", "Shutdown requested")
    # finally:
    #     print_status("info", "Stopping services")
    #     for name, proc in processes:
    #         if proc.poll() is None:
    #             proc.terminate()
    #             try:
    #                 proc.wait(timeout=5)
    #                 print_status("ok", f"{name} stopped")
    #             except subprocess.TimeoutExpired:
    #                 proc.kill()
    #                 print_status("warn", f"{name} killed")


if __name__ == "__main__":
    main()
