#!/usr/bin/env python3
"""
LANFXplorer Main Entry Point

Orchestrates the complete application startup in order:
1. startsetup.py - PKI and environment setup
2. receive.py - QUIC receiver (background)
3. api_bridge.py - Flask API (background)
4. lanfxplorer.AppImage / lanfxplorer.exe - UI
"""
import os
import sys
from pathlib import Path

# CRITICAL: Set up paths FIRST, before importing any local modules
APP_DIR = Path(__file__).parent.resolve()
os.chdir(APP_DIR)
sys.path.insert(0, str(APP_DIR))

# Now import other standard library modules
import subprocess
import time
import platform
import signal

# Now we can safely import local modules
from startsetup import write_env


def print_status(status: str, message: str):
    symbols = {"ok": "✓", "fail": "✗", "info": "ℹ", "warn": "⚠", "run": "→"}
    print(f"[{symbols.get(status, '•')}] {message}")


def cleanup_existing_services():
    """
    Kill any existing Python processes using our service ports.
    This prevents 'address already in use' errors on restart.
    
    Ports used:
    - 4433: QUIC File Transfer
    - 4434: CA Discovery
    - 4435: CA Signing
    - 4436: Peer Discovery
    - 4437: Handshake Service
    - 5000: Flask API
    """
    if platform.system().lower() == "windows":
        # Windows: use netstat and taskkill
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=10
            )
            pids_to_kill = set()
            for line in result.stdout.splitlines():
                for port in ["4433", "4434", "4435", "4436", "4437", "5000"]:
                    if f":{port}" in line and "LISTENING" in line:
                        parts = line.split()
                        if parts:
                            pids_to_kill.add(parts[-1])
            
            for pid in pids_to_kill:
                if pid.isdigit() and pid != str(os.getpid()):
                    try:
                        subprocess.run(["taskkill", "/F", "/PID", pid], 
                                      capture_output=True, timeout=5)
                        print_status("info", f"Killed existing process (PID {pid})")
                    except Exception:
                        pass
        except Exception:
            pass
    else:
        # Linux: use ss or lsof to find and kill processes
        try:
            result = subprocess.run(
                ["ss", "-tunlp"],
                capture_output=True, text=True, timeout=10
            )
            pids_to_kill = set()
            for line in result.stdout.splitlines():
                for port in ["4433", "4434", "4435", "4436", "4437", "5000"]:
                    if f":{port}" in line and "python" in line.lower():
                        # Extract PID from output like "users:(("python3",pid=12345,fd=10))"
                        import re
                        match = re.search(r'pid=(\d+)', line)
                        if match:
                            pids_to_kill.add(int(match.group(1)))
            
            current_pid = os.getpid()
            for pid in pids_to_kill:
                if pid != current_pid:
                    try:
                        os.kill(pid, signal.SIGTERM)
                        print_status("info", f"Killed existing process (PID {pid})")
                    except ProcessLookupError:
                        pass  # Process already gone
                    except PermissionError:
                        print_status("warn", f"Cannot kill PID {pid} (permission denied)")
            
            # Brief pause to allow sockets to be released
            if pids_to_kill:
                time.sleep(1)
                
        except FileNotFoundError:
            # ss not available, try lsof
            try:
                for port in ["4433", "4434", "4435", "4436", "4437", "5000"]:
                    result = subprocess.run(
                        ["lsof", "-t", f"-i:{port}"],
                        capture_output=True, text=True, timeout=5
                    )
                    for pid_str in result.stdout.strip().split():
                        if pid_str.isdigit():
                            pid = int(pid_str)
                            if pid != os.getpid():
                                try:
                                    os.kill(pid, signal.SIGTERM)
                                    print_status("info", f"Killed existing process (PID {pid})")
                                except Exception:
                                    pass
            except Exception:
                pass
        except Exception:
            pass


def run_script(script_name: str, wait: bool = True):
    script_path = APP_DIR / script_name
    if not script_path.exists():
        print_status("fail", f"Script not found: {script_path}")
        return None

    print_status("run", f"Starting {script_name}")
    # Don't capture output for scripts we wait for - let it display in real-time
    proc = subprocess.Popen(
        [sys.executable, str(script_path)],
        cwd=str(APP_DIR),
        stdout=None,
        stderr=None,
    )

    if wait:
        proc.wait()
        if proc.returncode != 0:
            print_status("fail", f"{script_name} exited with code {proc.returncode}")
            return None
    else:
        time.sleep(1)
        if proc.poll() is not None:
            return None

    return proc


def run_ui():
    # Headless mode (set by app_32bit.sh / app_32bit.bat)
    if os.environ.get("LANFXPLORER_HEADLESS"):
        print_status("info", "Headless mode — UI skipped")
        print_status("info", "Backend running. Access API at http://localhost:5000")
        return None

    # Platform-specific UI paths, with debug (development) fallback
    if platform.system().lower() == "windows":
        ui_path = APP_DIR / "build" / "windows" / "x64" / "runner" / "Release" / "lanfxplorer.exe"
    else:
        # Linux: try debug build first (development), then release (custom build)
        debug_path = APP_DIR / "build" / "linux" / "x64" / "debug" / "bundle" / "lanfxplorer"
        release_path = APP_DIR / "build" / "linux" / "x64" / "release" / "bundle" / "lanfxplorer"
        ui_path = debug_path if debug_path.exists() else release_path
    
    if not os.path.exists(ui_path):
        print_status("fail", f"UI executable not found: {ui_path}")
        return None

    # Check architecture compatibility (Flutter UI is x64 only)
    import struct
    if struct.calcsize("P") * 8 == 32:
        print_status("warn", "UI binary is x64 — skipping on 32-bit system")
        print_status("info", "Backend running headless. Access API at http://localhost:5000")
        return None

    print_status("run", "Starting LANFXplorer UI")
    try:
        return subprocess.Popen([str(ui_path)], cwd=str(APP_DIR))
    except OSError as e:
        print_status("warn", f"Cannot launch UI: {e}")
        print_status("info", "Backend running headless. Access API at http://localhost:5000")
        return None


def main():
    processes = []
    
    # Kill any existing processes using our ports to prevent 'address already in use'
    print_status("info", "Cleaning up existing services...")
    cleanup_existing_services()
    
    # Run setup - critical for environment configuration
    setup_result = run_script("startsetup.py", wait=True)
    if not setup_result:
        print_status("fail", "Setup failed - cannot continue")
        return
    
    time.sleep(2)  # Brief pause to ensure .env is written to disk
    receiver = run_script("receive.py", wait=False)
    if not receiver:
        return
    processes.append(("Receiver", receiver))

    time.sleep(5)

    api = run_script("api_bridge.py", wait=False)
    if api:
        processes.append(("API Bridge", api))

    time.sleep(2)

    ui_proc = run_ui()
    if ui_proc:
        processes.append(("UI", ui_proc))
        ui_proc.wait()
    else:
        # No UI (32-bit or missing binary) — run headless, wait for Ctrl+C
        print_status("info", "Running in headless mode. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print_status("info", "Shutdown requested")

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
