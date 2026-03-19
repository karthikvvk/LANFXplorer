#!/usr/bin/env python3
"""
LANFXplorer Main Entry Point
"""

import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).parent.resolve()
os.chdir(APP_DIR)
sys.path.insert(0, str(APP_DIR))

import subprocess
import time
import platform
import signal

from startsetup import write_env


def print_status(status: str, message: str):
    symbols = {"ok": "✓", "fail": "✗", "info": "ℹ", "warn": "⚠", "run": "→"}
    print(f"[{symbols.get(status, '•')}] {message}")


def cleanup_existing_services():
    try:
        result = subprocess.run(["ss", "-tunlp"], capture_output=True, text=True, timeout=10)
        pids_to_kill = set()

        for line in result.stdout.splitlines():
            for port in ["4433", "4434", "4435", "4436", "4437", "5000"]:
                if f":{port}" in line and "python" in line.lower():
                    import re
                    match = re.search(r'pid=(\d+)', line)
                    if match:
                        pids_to_kill.add(int(match.group(1)))

        current_pid = os.getpid()
        for pid in pids_to_kill:
            if pid != current_pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                    print_status("info", f"Killed PID {pid}")
                except Exception:
                    pass

        if pids_to_kill:
            time.sleep(1)

    except Exception:
        pass


def run_script(script_name: str, wait: bool = True):
    script_path = APP_DIR / script_name
    if not script_path.exists():
        print_status("fail", f"Missing: {script_name}")
        return None

    print_status("run", f"Starting {script_name}")

    proc = subprocess.Popen(
        [sys.executable, str(script_path)],
        cwd=str(APP_DIR),
    )

    if wait:
        proc.wait()
        if proc.returncode != 0:
            return None
    else:
        time.sleep(1)
        if proc.poll() is not None:
            return None

    return proc


# ─────────────────────────────────────────────
# NEW: unified elevation function (popup-first)
# ─────────────────────────────────────────────
def elevate_and_run(script_path: str):
    import shutil

    system = platform.system().lower()
    elevated_ok = False

    try:
        if system == "windows":
            ps_cmd = (
                f"$p = Start-Process '{sys.executable}' "
                f"-ArgumentList '\"{script_path}\" --install' "
                f"-Verb RunAs -Wait -PassThru; exit $p.ExitCode"
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd]
            )
            elevated_ok = (res.returncode == 0)

        else:
            display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")

            # ── 1. pkexec (BEST) ──
            if shutil.which("pkexec"):
                print_status("run", "Using pkexec (GUI auth)")
                print(f"pkexec {sys.executable} {script_path} --install")
                res = os.system(f"pkexec {sys.executable} {script_path} --install")
                # elevated_ok = (res.returncode == 0)

            # ── 2. GUI password prompt ──
            elif display and (shutil.which("zenity") or shutil.which("kdialog")):
                print_status("run", "Using GUI password prompt")

                if shutil.which("zenity"):
                    pw_cmd = [
                        "zenity", "--password",
                        "--title=LANFXplorer",
                        "--text=Enter sudo password"
                    ]
                else:
                    pw_cmd = ["kdialog", "--password", "Enter sudo password"]

                pw = subprocess.run(pw_cmd, capture_output=True, text=True)

                if pw.returncode == 0:
                    password = pw.stdout.strip()

                    res = subprocess.run(
                        ["sudo", "-S", sys.executable, script_path, "--install"],
                        input=password + "\n",
                        text=True
                    )
                    elevated_ok = (res.returncode == 0)
                else:
                    print_status("warn", "Password dialog cancelled")

            # ── 3. fallback ──
            else:
                print_status("warn", "Falling back to terminal sudo")
                res = subprocess.run(
                    ["sudo", sys.executable, script_path, "--install"]
                )
                elevated_ok = (res.returncode == 0)

    except Exception as e:
        print_status("fail", f"Elevation error: {e}")

    return elevated_ok


def main():
    print_status("info", "Cleaning services")
    cleanup_existing_services()

    # ── connectivity check ──
    def ping():
        try:
            return subprocess.run(["ping", "-c", "1", "-W", "2", "127.0.0.1"]).returncode == 0
        except:
            return False

    if not ping():
        print_status("warn", "Network issue detected")

        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()

            if messagebox.askyesno(
                "Firewall Required",
                "Fix firewall rules?\nRequires admin privileges."
            ):
                fw_script = str(APP_DIR / "firewall_manager.py")

                if elevate_and_run(fw_script):
                    print_status("ok", "Firewall configured")
                else:
                    print_status("fail", "Firewall setup failed")

            root.destroy()

        except Exception:
            print_status("warn", "No GUI available")

    # ── setup ──
    if not run_script("startsetup.py", True):
        return

    time.sleep(2)

    receiver = run_script("receive.py", False)
    if not receiver:
        return

    time.sleep(5)

    api = run_script("api_bridge.py", False)

    print_status("ok", "System running")

    # ── UI ──
    import struct
    arch_bits = struct.calcsize("P") * 8
    headless = os.environ.get("LANFXPLORER_HEADLESS") == "1"
    display   = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    system = platform.system().lower()

    ui_launched = False

    if not headless and (display or system == "windows"):
        if arch_bits == 64:
            if system == "windows":
                flutter_bin = APP_DIR / "build" / "windows" / "x64" / "runner" / "Release" / "lanfxplorer.exe"
            else:
                flutter_bin = APP_DIR / "build" / "linux" / "x64" / "release" / "bundle" / "lanfxplorer"

            if flutter_bin.exists():
                print_status("run", f"Starting Flutter UI ({flutter_bin.name})")
                try:
                    # Run without overriding cwd so it finds .env in the project root
                    ui_launched = True
                    subprocess.run([str(flutter_bin)])
                    # ui_launched = True
                except KeyboardInterrupt:
                    pass  # Ctrl+C from user — clean exit
                except Exception as e:
                    print_status("warn", f"Flutter UI failed: {e}. Falling back to Tkinter...")

        if not ui_launched:
            try:
                print_status("run", "Starting Tkinter UI")
                sys.path.insert(0, str(APP_DIR / "32bitscreens"))
                import tkinter_app
                tkinter_app.main()          # blocks until window is closed
                ui_launched = True
            except KeyboardInterrupt:
                pass  # Ctrl+C from user — clean exit
            except Exception as e:
                print_status("warn", f"Tkinter UI failed to start: {e}")

    if not ui_launched:
        if headless:
            print_status("info", "Headless mode — UI suppressed")
        else:
            print_status("warn", "No UI could be started — running headless")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    print_status("info", "Shutdown")


if __name__ == "__main__":
    main()