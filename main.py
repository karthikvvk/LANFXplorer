#!/usr/bin/env python3
"""
LANFXplorer Main Entry Point

Supports two run modes:
  - Normal (GUI): starts backend + Flutter/Tkinter UI
  - Headless service (LANFXPLORER_HEADLESS=1): starts backend only,
    notifies systemd via sd_notify, and blocks until SIGTERM.
"""

import json
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

# ── PID-file directory ────────────────────────────────────────────────────────
# Stores one JSON file per managed subprocess:
#   { "pid": <int>, "started": <float epoch> }
# Files survive crashes; they are cleaned up on normal shutdown.
_PID_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lanfxplorer"

# Script stem → PID file name
_PID_FILES = {
    "receive.py":    _PID_DIR / "receiver.pid",
    "api_bridge.py": _PID_DIR / "api.pid",
}


def _write_pid(script_name: str, proc: subprocess.Popen) -> None:
    """Write {pid, started} to the PID file for *script_name*."""
    pid_path = _PID_FILES.get(script_name)
    if pid_path is None:
        return
    try:
        _PID_DIR.mkdir(parents=True, exist_ok=True)
        # Read process start time from /proc (Linux) for reuse-proof verification.
        started = _get_proc_start_time(proc.pid)
        pid_path.write_text(json.dumps({"pid": proc.pid, "started": started}))
    except Exception as exc:
        print_status("warn", f"Could not write PID file for {script_name}: {exc}")


def _delete_pid(script_name: str) -> None:
    """Delete the PID file for *script_name* (called on clean shutdown)."""
    pid_path = _PID_FILES.get(script_name)
    if pid_path and pid_path.exists():
        try:
            pid_path.unlink()
        except Exception:
            pass


def _get_proc_start_time(pid: int) -> float:
    """
    Return process start time as a float (seconds since boot on Linux,
    or 0.0 if unavailable).  Used to detect PID reuse.
    """
    try:
        # Linux: /proc/<pid>/stat field 22 is start-time in clock ticks
        stat = Path(f"/proc/{pid}/stat").read_text()
        # Field 22 is after the comm field which may contain spaces/parens
        after_comm = stat[stat.rfind(")") + 2:]
        fields = after_comm.split()
        ticks = int(fields[19])   # index 19 = field 22 (0-indexed from after comm)
        clk_tck = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
        return ticks / clk_tck
    except Exception:
        pass
    try:
        # Cross-platform fallback via psutil (optional dep)
        import psutil
        return psutil.Process(pid).create_time()
    except Exception:
        return 0.0


def _kill_from_pid_file(script_name: str) -> None:
    """
    Read the PID file for *script_name*, verify the process still belongs
    to us (by cmdline + start-time), then terminate it.

    Verification prevents killing an unrelated process that reused the PID.
    """
    pid_path = _PID_FILES.get(script_name)
    if pid_path is None or not pid_path.exists():
        return

    try:
        data = json.loads(pid_path.read_text())
        pid = int(data["pid"])
        stored_started = float(data.get("started", 0))
    except Exception as exc:
        print_status("warn", f"Bad PID file for {script_name}: {exc}")
        return

    if pid <= 0:
        return

    # ── Verify cmdline still looks like our script ────────────────────────────
    try:
        cmdline_path = Path(f"/proc/{pid}/cmdline")
        if cmdline_path.exists():
            cmdline = cmdline_path.read_bytes().replace(b"\x00", b" ").decode(errors="replace")
            stem = script_name  # e.g. "receive.py"
            if stem not in cmdline:
                print_status("warn", f"PID {pid} cmdline does not contain '{stem}' — skipping kill")
                return
        # else: /proc not available (non-Linux), skip cmdline check
    except Exception:
        pass

    # ── Verify start-time to catch PID reuse ─────────────────────────────────
    current_started = _get_proc_start_time(pid)
    if stored_started and current_started and abs(current_started - stored_started) > 1.0:
        print_status("warn", f"PID {pid} start-time mismatch (PID reuse detected) — skipping kill")
        return

    # ── Terminate ─────────────────────────────────────────────────────────────
    try:
        if platform.system().lower() != "windows":
            # Kill the entire process group so MsQuic child processes also die
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)
                print_status("info", f"Sent SIGTERM to process group {pgid} ({script_name})")
            except ProcessLookupError:
                pass   # process already gone
        else:
            os.kill(pid, signal.SIGTERM)
            print_status("info", f"Sent SIGTERM to PID {pid} ({script_name})")
    except Exception as exc:
        print_status("warn", f"Could not kill {script_name} (PID {pid}): {exc}")

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
    # ── Stop the systemd background service first (if it is running) ─────────
    # This ensures the service's child processes (receive.py, api_bridge.py)
    # are cleanly terminated before we start fresh ones below.
    #
    # Guard: when THIS process IS the service (LANFXPLORER_HEADLESS=1) we must
    # NOT stop ourselves — that would kill the service on every startup.
    _is_service = os.environ.get("LANFXPLORER_HEADLESS") == "1"
    if not _is_service:
        try:
            svc_check = subprocess.run(
                ["systemctl", "--user", "is-active", "lanfxplorer-backend"],
                capture_output=True, text=True, timeout=5,
            )
            if svc_check.stdout.strip() == "active":
                print_status("info", "Stopping lanfxplorer-backend service...")
                subprocess.run(
                    ["systemctl", "--user", "stop", "lanfxplorer-backend"],
                    timeout=15,
                )
                time.sleep(1)   # let ports fully release
                print_status("ok", "Service stopped")
        except Exception as e:
            print_status("warn", f"Could not stop service (non-fatal): {e}")

    # ── Kill previous instances via PID files ─────────────────────────────────
    # PID files are written by run_script() below and contain {pid, started}.
    # Verification ensures we only kill our own processes — not a different
    # program that happened to reuse the same PID (PID-reuse defence).
    for script_name in list(_PID_FILES):
        _kill_from_pid_file(script_name)

    # Brief pause so freed ports are available before we re-bind.
    time.sleep(0.5)


def run_script(script_name: str, wait: bool = True):
    """
    Launch *script_name* as a subprocess.

    Background processes (wait=False) are started in a new process group so
    that killing the group also terminates any grandchildren (e.g. the MsQuic
    binary spawned by receive.py).  Their stdout/stderr are redirected to
    separate log files under APP_DIR/logs/.
    """
    script_path = APP_DIR / script_name
    if not script_path.exists():
        print_status("fail", f"Missing: {script_name}")
        return None

    print_status("run", f"Starting {script_name}")

    _system = platform.system().lower()

    if wait:
        # Foreground scripts (startsetup.py) share the terminal — no special flags.
        proc = subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=str(APP_DIR),
        )
        proc.wait()
        if proc.returncode != 0:
            return None
        return proc

    # ── Background subprocess setup ───────────────────────────────────────────
    # Redirect to a dedicated log file so all three processes don't interleave
    # on the same terminal (makes debugging significantly easier).
    log_dir = APP_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    stem = Path(script_name).stem          # "receive" or "api_bridge"
    log_fh = open(log_dir / f"{stem}.log", "a", buffering=1)  # line-buffered

    popen_kwargs = dict(
        cwd=str(APP_DIR),
        stdout=log_fh,
        stderr=log_fh,
    )

    if _system != "windows":
        # start_new_session=True puts the process in its own session/process-group.
        # os.killpg() on shutdown then kills the entire tree (including MsQuic).
        popen_kwargs["start_new_session"] = True
    else:
        # On Windows, CREATE_NEW_PROCESS_GROUP allows sending CTRL_BREAK_EVENT
        # to the process group for clean shutdown.
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        [sys.executable, str(script_path)],
        **popen_kwargs,
    )

    # Brief health-check: if process exits immediately it's a hard failure.
    time.sleep(1)
    if proc.poll() is not None:
        print_status("fail", f"{script_name} exited immediately (rc={proc.returncode}). "
                             f"Check logs/{stem}.log")
        return None

    # Persist PID + start-time so cleanup_existing_services() can find and
    # kill this process precisely on the next startup.
    _write_pid(script_name, proc)
    print_status("info", f"{script_name} running (PID {proc.pid}) → logs/{stem}.log")
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
            # Use subprocess.run() with a list — never os.system() with an f-string.
            # os.system() passes the command through /bin/sh, making it vulnerable
            # to shell injection if script_path contains spaces or special characters.
            if shutil.which("pkexec"):
                print_status("run", "Using pkexec (GUI auth)")
                res = subprocess.run(
                    ["pkexec", sys.executable, str(script_path), "--install"]
                )
                elevated_ok = (res.returncode == 0)

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
                        ["sudo", "-S", sys.executable, str(script_path), "--install"],
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
                    ["sudo", sys.executable, str(script_path), "--install"]
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
            # ── Try frozen py_ui binary (distribution package) ────────────────
            # Builder places both binaries in APP_DIR/py_ui_64/:
            #   py_ui_64   — built on 64-bit (via builder.py)
            #   py_ui_32   — manually dropped in from a 32-bit build
            _py_ui_dir = APP_DIR / "py_ui_64"
            if system == "windows":
                _py_ui_bin = _py_ui_dir / (f"py_ui_{arch_bits}.exe")
            else:
                _py_ui_bin = _py_ui_dir / f"py_ui_{arch_bits}"

            if _py_ui_bin.exists() and os.access(str(_py_ui_bin), os.X_OK):
                print_status("run", f"Starting Python UI ({_py_ui_bin.name})")
                try:
                    subprocess.run([str(_py_ui_bin)])
                    ui_launched = True
                except KeyboardInterrupt:
                    pass
                except Exception as e:
                    print_status("warn", f"Frozen UI failed: {e}. Falling back to module import...")

        if not ui_launched:
            try:
                print_status("run", "Starting Tkinter UI (module)")
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
    _system = platform.system().lower()

    # Terminate child processes (receiver, api_bridge) and their entire process
    # groups (which include grandchildren like the MsQuic binary).
    for child_name, child_proc in (("receive.py", receiver), ("api_bridge.py", api)):
        if child_proc and child_proc.poll() is None:
            print_status("info", f"Stopping {child_name} (PID {child_proc.pid})")
            try:
                if _system != "windows":
                    # Kill the whole process group — terminates MsQuic grandchildren too
                    try:
                        pgid = os.getpgid(child_proc.pid)
                        os.killpg(pgid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                else:
                    # Windows: send CTRL_BREAK_EVENT to the process group
                    child_proc.send_signal(signal.CTRL_BREAK_EVENT)
            except Exception:
                child_proc.terminate()   # fallback
            try:
                child_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    if _system != "windows":
                        os.killpg(os.getpgid(child_proc.pid), signal.SIGKILL)
                    else:
                        child_proc.kill()
                except Exception:
                    pass
        # Clean up PID file on successful shutdown
        _delete_pid(child_name)


if __name__ == "__main__":
    main()

# TODO(netlink): wait_for_interface_ready() currently polls via subprocess every 0.5 s.
# A cleaner Linux alternative is pyroute2 Netlink — the kernel notifies on interface/IP
# change events with no polling required. Acceptable as-is for now.
