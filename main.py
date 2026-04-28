#!/usr/bin/env python3
"""
LANFXplorer Main Entry Point

Supports two run modes:
  - Normal (GUI): starts backend + Flutter/Tkinter UI
  - Headless service (LANFXPLORER_HEADLESS=1): starts backend only,
    notifies systemd via sd_notify, and blocks until SIGTERM.
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
import threading

from startsetup import write_env

# ── systemd sd_notify helper ──────────────────────────────────────────────────
def _sd_notify(state: str) -> None:
    """Send a notification string to systemd via $NOTIFY_SOCKET if available.

    Allows systemd to track service readiness (Type=notify would need
    sd_notify; with Type=simple this is a best-effort quality-of-life
    improvement for accurate `systemctl status` output).
    """
    sock_path = os.environ.get("NOTIFY_SOCKET")
    if not sock_path:
        return
    try:
        import socket as _sock
        with _sock.socket(_sock.AF_UNIX, _sock.SOCK_DGRAM) as s:
            if sock_path.startswith("@"):
                sock_path = "\x00" + sock_path[1:]
            s.sendto(state.encode(), sock_path)
    except Exception:
        pass


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


def wait_for_interface_ready(timeout: int = 20) -> bool:
    """
    Poll until the IP written by startsetup.py is actually assigned on the
    interface reported in .env.  This closes the race-window between
    nmcli activating the p2p-link and Flask/receiver trying to bind.

    Returns True if the IP became visible before *timeout* seconds,
    False if we timed out (callers should continue anyway with a warning).
    """
    import re as _re
    from app_config import get_config

    try:
        cfg = get_config()
        cfg.reload()
        iface   = cfg.interface
        host_ip = cfg.host
    except Exception:
        return False

    if not iface or not host_ip:
        return False

    # Loopback or already-known-good addresses need no wait
    if host_ip.startswith("127."):
        return True

    print_status("run", f"Waiting for {iface} to be ready with IP {host_ip}...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            out = subprocess.check_output(
                ["ip", "-o", "-4", "addr", "show", iface],
                text=True, stderr=subprocess.DEVNULL
            )
            if host_ip in out:
                print_status("ok", f"{iface} is up with {host_ip}")
                return True
        except Exception:
            pass
        time.sleep(0.5)

    print_status("warn", f"Timed out waiting for {iface}/{host_ip} — continuing anyway")
    return False


def main():
    print_status("info", "Cleaning services")
    cleanup_existing_services()

    # ── setup ──
    if not run_script("startsetup.py", True):
        return

    # Wait for the network interface to be fully ready before binding services.
    # This prevents Flask from displaying 127.0.0.1 instead of the real IP,
    # and ensures the QUIC receiver won't bind before the p2p-link is active.
    wait_for_interface_ready(timeout=20)

    receiver = run_script("receive.py", False)
    if not receiver:
        return

    time.sleep(3)

    api = run_script("api_bridge.py", False)

    print_status("ok", "System running")

    # ── Systemd readiness notification ──────────────────────────────────────
    # Tell systemd the service is ready.  Harmless when not running under
    # systemd (NOTIFY_SOCKET will be absent and the call is a no-op).
    _sd_notify("READY=1\nSTATUS=LANFXplorer backend running")

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
        # ── Headless / service mode ───────────────────────────────────────────
        # Block here until systemd sends SIGTERM (or user sends SIGINT/SIGTERM).
        # Use an Event so the signal handler can wake us up cleanly without
        # relying on KeyboardInterrupt (which SIGTERM does NOT raise).
        if headless:
            print_status("info", "Headless mode — UI suppressed. Backend services active.")
        else:
            print_status("warn", "No UI could be started — running headless")

        _shutdown = threading.Event()

        def _handle_stop(signum, frame):  # noqa: ANN001
            print_status("info", f"Received signal {signum} — initiating shutdown")
            _sd_notify("STOPPING=1")
            _shutdown.set()

        signal.signal(signal.SIGTERM, _handle_stop)
        signal.signal(signal.SIGINT,  _handle_stop)

        print_status("info", "Waiting for stop signal (SIGTERM/SIGINT)...")

        # ── Watchdog keepalive ────────────────────────────────────────────────────
        # systemd sets WATCHDOG_USEC when WatchdogSec is configured in the unit.
        # We must send WATCHDOG=1 within that interval or systemd will consider the
        # service hung and restart it.  We ping at half the interval (safe margin).
        _watchdog_usec = int(os.environ.get("WATCHDOG_USEC", 0))
        if _watchdog_usec > 0:
            _ping_interval = max(1.0, (_watchdog_usec / 1_000_000) / 2)
            print_status("info", f"Watchdog enabled — pinging systemd every {_ping_interval:.0f}s")

            def _watchdog_loop():
                while not _shutdown.is_set():
                    _sd_notify("WATCHDOG=1")
                    _shutdown.wait(timeout=_ping_interval)

            _wd_thread = threading.Thread(target=_watchdog_loop, name="watchdog", daemon=True)
            _wd_thread.start()
        else:
            # No watchdog configured — plain wait is fine.
            pass

        _shutdown.wait()  # Block until SIGTERM / SIGINT

    print_status("info", "Shutdown")
    # Terminate child processes (receiver, api_bridge) if still alive
    for child_name, child_proc in (("receive.py", receiver), ("api_bridge.py", api)):
        if child_proc and child_proc.poll() is None:
            print_status("info", f"Stopping {child_name} (PID {child_proc.pid})")
            child_proc.terminate()
            try:
                child_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child_proc.kill()


if __name__ == "__main__":
    main()