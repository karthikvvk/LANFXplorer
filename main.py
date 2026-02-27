#!/usr/bin/env python3
"""
LANFXplorer Main Entry Point

Orchestrates the complete application startup in order:
1. startsetup.py - PKI and environment setup
2. receive.py - QUIC receiver (background)
3. api_bridge.py - Flask API (background)
4. UI launch: Flutter (64-bit) → Python UI (32-bit) → headless CLI (fallback)
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
    """Try to launch a UI in order: Flutter (64-bit) → Python UI (32-bit) → headless."""

    # Explicit headless mode (set by --headless flag or app_32bit.sh/bat)
    if os.environ.get("LANFXPLORER_HEADLESS"):
        print_status("info", "Headless mode — UI skipped")
        print_status("info", "Backend running. Access API at http://localhost:5000")
        return None

    import struct
    is_32bit = struct.calcsize("P") * 8 == 32

    # ── 32-bit systems: try Python UI first, then fall back to headless CLI ──
    if is_32bit:
        print_status("info", "32-bit system detected — Flutter UI not available")
        print_status("info", "Trying Python UI...")

        # Try 1: PyInstaller-built executable (ships in release archive)
        if platform.system().lower().startswith("win"):
            pyinstaller_exe = APP_DIR / "python_ui" / "python_ui.exe"
        else:
            pyinstaller_exe = APP_DIR / "python_ui" / "python_ui"

        if pyinstaller_exe.exists():
            try:
                proc = subprocess.Popen(
                    [str(pyinstaller_exe)],
                    cwd=str(APP_DIR))
                print_status("ok", f"Python UI launched (PyInstaller): {pyinstaller_exe.name}")
                return proc
            except OSError as e:
                print_status("warn", f"Cannot launch Python UI executable: {e}")

        # Try 2: Run from source (development mode)
        tkinter_script = APP_DIR / "32bitscreens" / "tkinter_app.py"
        if tkinter_script.exists():
            try:
                proc = subprocess.Popen(
                    [sys.executable, str(tkinter_script)],
                    cwd=str(APP_DIR))
                print_status("ok", "Python UI launched (tkinter source)")
                return proc
            except OSError as e:
                print_status("warn", f"Cannot launch Tkinter UI: {e}")

        # Both Python UI attempts failed → fall back to headless CLI
        print_status("warn", "Python UI not available — falling back to headless CLI")
        os.environ["LANFXPLORER_HEADLESS"] = "1"
        print_status("info", "Backend running headless. Access API at http://localhost:5000")
        return None

    # ── 64-bit systems: try Flutter UI ──
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

    print_status("run", "Starting LANFXplorer UI")
    try:
        return subprocess.Popen([str(ui_path)], cwd=str(APP_DIR))
    except OSError as e:
        print_status("warn", f"Cannot launch UI: {e}")
        print_status("info", "Backend running headless. Access API at http://localhost:5000")
        return None


def main():
    processes = []

    # Headless mode: interactive CLI profile creation before anything else
    # (set by --headless flag, or dynamically by run_ui() when Python UI fails)
    if os.environ.get("LANFXPLORER_HEADLESS"):
        from cli_profile import ensure_profile
        if not ensure_profile():
            print_status("fail", "Profile creation cancelled — exiting")
            return
    
    # Kill any existing processes using our ports to prevent 'address already in use'
    print_status("info", "Cleaning up existing services...")
    cleanup_existing_services()
    
    # Quick connectivity check (ping gateway – 5 s timeout)
    try:
        import socket, struct as _st
        _bits = _st.calcsize("P") * 8

        def _quick_ping() -> bool:
            """Try to reach the default gateway via ICMP ping (5 s)."""
            gw = None
            system = platform.system().lower()

            if system != "windows":
                try:
                    # Detect gateway from /proc on Linux
                    with open("/proc/net/route") as f:
                        for line in f:
                            parts = line.strip().split()
                            if len(parts) >= 3 and parts[1] != "00000000":
                                continue
                            if parts[1] == "00000000" and parts[0] != "lo":
                                gw_hex = parts[2]
                                gw = socket.inet_ntoa(bytes.fromhex(gw_hex)[::-1] if sys.byteorder == "little"
                                                      else bytes.fromhex(gw_hex))
                                break
                except Exception:
                    pass
            else:
                # Windows: parse default gateway from ipconfig
                try:
                    r = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=5)
                    for line in (r.stdout or "").splitlines():
                        if "default gateway" in line.lower():
                            parts = line.split(":")
                            if len(parts) >= 2:
                                ip = parts[1].strip()
                                if ip:
                                    gw = ip
                                    break
                except Exception:
                    pass

            if not gw:
                # Fallback: try pinging localhost (services should be reachable)
                gw = "127.0.0.1"

            try:
                if system == "windows":
                    cmd = ["ping", "-n", "1", "-w", "5000", gw]
                else:
                    cmd = ["ping", "-c", "1", "-W", "5", gw]
                r = subprocess.run(cmd, capture_output=True, timeout=6)
                return r.returncode == 0
            except Exception:
                return False

        if not _quick_ping():
            print_status("warn", "Network ping failed – firewall may be blocking traffic")
            # Show a GUI popup if possible (Tk is always available for 32-bit)
            try:
                import tkinter as _tk
                from tkinter import messagebox as _mb
                _root = _tk.Tk()
                _root.withdraw()
                ans = _mb.askyesno(
                    "Firewall Required",
                    "Network ping failed. The firewall may be blocking "
                    "LANFXplorer.\n\n"
                    "Would you like to fix the firewall rules now?\n"
                    "(Requires administrator / sudo privileges)")
                _root.destroy()
                if ans:
                    import shutil
                    fw_script = str(APP_DIR / "firewall_manager.py")
                    if shutil.which("pkexec"):
                        cmd = ["pkexec", sys.executable, fw_script, "--install"]
                    else:
                        cmd = ["sudo", sys.executable, fw_script, "--install"]
                    print_status("run", f"Running: {' '.join(cmd)}")
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    if res.returncode == 0:
                        print_status("ok", "Firewall rules applied")
                    else:
                        print_status("fail", f"Firewall fix failed: {(res.stdout or '') + (res.stderr or '')}")
            except Exception as gui_err:
                print_status("warn", f"Could not show firewall popup: {gui_err}")
        else:
            print_status("ok", "Network connectivity OK")
    except Exception as e:
        print_status("warn", f"Connectivity check skipped: {e}")
    
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
        # No UI — run headless, wait for Ctrl+C
        # If headless was set dynamically (e.g. Python UI failed on 32-bit),
        # run CLI profile creation now before going into headless loop
        if os.environ.get("LANFXPLORER_HEADLESS") and not os.environ.get("_PROFILE_DONE"):
            from cli_profile import ensure_profile
            if not ensure_profile():
                print_status("fail", "Profile creation cancelled — exiting")
                return
            os.environ["_PROFILE_DONE"] = "1"

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
