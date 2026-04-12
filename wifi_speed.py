"""
Link Speed Detection Utility

Link Speed Detection Utility

Detects the negotiated link speed of the active Ethernet or WiFi interface
on Linux or Windows, preferring Ethernet when both are present.
Returns speed in Mbps for transfer time and chunk-size estimation.
"""
import platform
import subprocess
import re
from typing import Optional


def run_cmd(cmd):
    """Run a shell command and return output."""
    try:
        out = subprocess.check_output(
            cmd,
            stderr=subprocess.STDOUT,
            text=True
        )
        return out
    except subprocess.CalledProcessError as e:
        raise RuntimeError(e.output.strip())
    except FileNotFoundError:
        raise RuntimeError(f"Command not found: {cmd[0]}")

def get_linux_link_speed():
    """Get link speed on Linux — Ethernet first, WiFi fallback."""
    import glob
    import os as _os
    print("wifispeed")
    SKIP_PREFIXES = ("lo", "veth", "docker", "br-", "virbr", "vmnet", "cni", "tun", "tap")
    WIFI_PREFIXES = ("wlan", "wlp", "wl")

    # ── 1. Ethernet via /sys/class/net (no external tools required) ──────────
    try:
        for sys_path in sorted(glob.glob("/sys/class/net/*")):
            iface = _os.path.basename(sys_path)
            low   = iface.lower()

            # Skip loopback, virtual, and wireless interfaces
            if any(low == p or low.startswith(p) for p in SKIP_PREFIXES):
                continue
            if low.startswith(WIFI_PREFIXES):
                continue

            # Interface must be operationally up (some USB NICs report "unknown")
            operstate_path = _os.path.join(sys_path, "operstate")
            print(operstate_path, "operstate")
            try:
                with open(operstate_path) as f:
                    state = f.read().strip()
            except OSError:
                continue
            if state not in ("up", "unknown"):
                continue

            speed_path = _os.path.join(sys_path, "speed")
            if _os.path.exists(speed_path):
                try:
                    with open(speed_path) as f:
                        val = int(f.read().strip())
                        print(f"[wifi_speed] {iface}: {val} Mbps detected")
                    if val <= 0:
                        continue

                    # ── Renegotiation guard ─────────────────────────────────
                    # A USB ethernet adapter (or slow auto-neg) can come up at
                    # 10 Mbps on first plug even though the NIC supports GigE.
                    # If we see <= 10 Mbps, nudge ethtool to renegotiate and
                    # re-read once -- full auto-neg takes < 1 s in practice.
                    if val <= 10:
                        import time as _time
                        print(f"[wifi_speed] {iface}: only {val} Mbps detected "
                              f"-- trying to renegotiate link speed...")
                        try:
                            subprocess.run(
                                ["sudo", "ethtool", "-s", iface,
                                 "speed", "1000", "duplex", "full",
                                 "autoneg", "on"],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                timeout=5,
                            )
                            _time.sleep(1.5)
                            t = 10
                            while t > 0:
                                with open(speed_path) as f2:
                                    new_val = int(f2.read().strip())
                                if new_val > val:
                                    print(f"[wifi_speed] {iface}: renegotiated "
                                        f"to {new_val} Mbps")
                                    val = new_val
                                else:
                                    print(f"[wifi_speed] {iface}: still {val} Mbps "
                                        f"after renegotiation (adapter may "
                                        f"not support forced speed)")
                                t -= 1
                                _time.sleep(1)
                        except Exception as rn_err:
                            print(f"[wifi_speed] {iface}: renegotiation "
                                  f"skipped ({rn_err})")

                    return {
                        "interface": iface,
                        "rx_mbps":   float(val),
                        "tx_mbps":   float(val),
                        "type":      "ethernet",
                    }
                except Exception:
                    continue
    except Exception:
        pass
    # ── 2. WiFi via iwconfig ────────────────────────────────────────────────
    try:
        ip_out = run_cmd(["ip", "link", "show"])
        match  = re.search(r"\d+:\s+(wlan\d+|wlp\w+|wl\w+):", ip_out)
        if match:
            iface   = match.group(1)
            iwc_out = run_cmd(["iwconfig", iface])
            rate    = re.search(r"Bit Rate[:=]\s*([\d.]+)\s*Mb/s", iwc_out)
            if rate:
                bitrate = float(rate.group(1))
                return {"interface": iface, "rx_mbps": bitrate, "tx_mbps": bitrate, "type": "wifi"}
    except Exception:
        pass

    # ── 3. WiFi via `iw dev <iface> link` ───────────────────────────────────────
    try:
        ip_out = run_cmd(["ip", "link", "show"])
        match  = re.search(r"\d+:\s+(wlan\d+|wlp\w+|wl\w+):", ip_out)
        if match:
            iface  = match.group(1)
            iw_out = run_cmd(["iw", "dev", iface, "link"])
            # Typical line: "tx bitrate: 72.2 MBit/s"
            rate   = re.search(r"tx bitrate:\s*([\d.]+)\s*MBit/s", iw_out)
            if rate:
                bitrate = float(rate.group(1))
                return {"interface": iface, "rx_mbps": bitrate, "tx_mbps": bitrate, "type": "wifi"}
    except Exception:
        pass

    raise RuntimeError("No active network connection with detectable speed found")

def get_windows_link_speed():
    """Get link speed on Windows — Ethernet first, WiFi fallback."""
    import json as _json

    WIRELESS_KEYWORDS = ("wi-fi", "wifi", "wireless", "wlan", "802.11")

    # ── 1. Wired Ethernet via PowerShell (excludes wireless adapters) ────────
    try:
        ps_cmd = (
            'Get-NetAdapter | '
            'Where-Object { '
            '  $_.Status -eq "Up" -and '
            r'  $_.InterfaceDescription -notmatch "Wi-Fi|Wireless|802\.11|WLAN|WiFi" -and '
            '  $_.Name -notmatch "Wi-Fi|Wireless|WiFi" '
            '} | Select-Object Name, LinkSpeed | ConvertTo-Json'
        )
        output   = run_cmd(["powershell", "-Command", ps_cmd])
        adapters = _json.loads(output)
        if not isinstance(adapters, list):
            adapters = [adapters]
        for adapter in adapters:
            if not adapter:
                continue
            speed_str = adapter.get("LinkSpeed", "")
            name      = adapter.get("Name", "Ethernet")
            match = re.search(r"([\d.]+)\s*(G|M|K)?bps", speed_str, re.IGNORECASE)
            if match:
                val  = float(match.group(1))
                unit = (match.group(2) or "M").upper()
                if unit == "G":
                    val *= 1000
                elif unit == "K":
                    val /= 1000
                if val > 0:
                    return {"interface": name, "rx_mbps": val, "tx_mbps": val, "type": "ethernet"}
    except Exception:
        pass

    # ── 2. Wired Ethernet via WMIC (fallback if PowerShell fails) ────────────
    try:
        wmic_out = run_cmd(["wmic", "nic", "where", "NetEnabled='true'", "get",
                            "Name,Speed", "/format:csv"])
        for line in wmic_out.splitlines():
            line = line.strip()
            if not line or "Node" in line:
                continue
            parts = line.split(",")
            if len(parts) < 3:
                continue
            name = parts[-2]
            # Skip wireless adapters
            if any(kw in name.lower() for kw in WIRELESS_KEYWORDS):
                continue
            try:
                speed_mbps = float(parts[-1]) / 1_000_000
                if speed_mbps > 0:
                    return {"interface": name, "rx_mbps": speed_mbps,
                            "tx_mbps": speed_mbps, "type": "ethernet"}
            except ValueError:
                continue
    except Exception:
        pass

    # ── 3. WiFi via netsh wlan (last resort) ──────────────────────────────
    try:
        output = run_cmd(["netsh", "wlan", "show", "interfaces"])
        if "connected" in output.lower():
            rx    = re.search(r"Receive rate \(Mbps\)\s*:\s*(\d+)", output)
            tx    = re.search(r"Transmit rate \(Mbps\)\s*:\s*(\d+)", output)
            iface = re.search(r"Interface name\s*:\s*(.+)", output)
            if rx and tx:
                return {
                    "interface": iface.group(1).strip() if iface else "Wi-Fi",
                    "rx_mbps":   float(rx.group(1)),
                    "tx_mbps":   float(tx.group(1)),
                    "type":      "wifi",
                }
    except Exception:
        pass

    raise RuntimeError("Failed to detect any network link speeds")


def get_wifi_speed():
    """
    Get negotiated network link speed in Mbps.
    Returns None if speed cannot be determined.
    Maintains function name `get_wifi_speed` for backward compatibility.
    """
    os_type = platform.system()
    
    try:
        if os_type == "Linux":
            info = get_linux_link_speed()
        elif os_type == "Windows":
            info = get_windows_link_speed()
        else:
            return None
        
        # Return the lower of rx/tx as conservative estimate
        return min(info["rx_mbps"], info["tx_mbps"])
    except Exception as e:
        print(f"[wifi_speed] Could not detect link speed: {e}")
        return None


def calculate_optimal_chunk_size(
    speed_mbps: Optional[float] = None,
    file_size_bytes: Optional[int] = None,
) -> int:
    if speed_mbps is None:
        val = get_wifi_speed()
        if val is None:
            return 16 * 1024 * 1024 #64 * 1024
        speed = float(val)
    else:
        speed = float(speed_mbps)

    if speed <= 0.0:
        return 16 * 1024 * 1024 #64 * 1024  # 64 KB fallback

    # Base chunk per speed tier
    if speed <= 50.0:
        chunk = 256 * 1024              # 256 KB — slow link / USB 2.0 NIC
    elif speed <= 150.0:
        chunk = 1 * 1024 * 1024         # 1 MB   — 100 Mbps Ethernet / 802.11n
    elif speed <= 500.0:
        chunk = 4 * 1024 * 1024         # 4 MB   — Gigabit / 802.11ac
    elif speed <= 2500.0:
        chunk = 8 * 1024 * 1024         # 8 MB   — 2.5 GbE
    else:
        chunk = 16 * 1024 * 1024        # 16 MB  — 10 GbE+

    # Large-file boost: double the chunk for files > 500 MB
    if file_size_bytes and file_size_bytes > 500 * 1024 * 1024:
        chunk = chunk * 2

    return chunk

def estimate_transfer_time_seconds(file_size_bytes: int, speed_mbps: Optional[float] = None) -> float:
    """
    Estimate transfer time in seconds based on file size and WiFi speed.
    Uses 90% of negotiated speed as realistic estimate.
    
    Args:
        file_size_bytes: Size of file to transfer in bytes
        speed_mbps: WiFi speed in Mbps, or None to auto-detect
        
    Returns:
        Estimated time in seconds, or 0 if cannot determine
    """
    if speed_mbps is None:
        val = get_wifi_speed()
        if val is None:
            return 0.0
        speed = float(val)
    else:
        speed = float(speed_mbps)
    
    if speed <= 0.0:
        return 0.0
        
    # Use 90% of negotiated speed (10% reduction for overhead/real-world)
    effective_speed_mbps = speed * 0.9
    
    # Convert Mbps to bytes per second: Mbps * 1_000_000 / 8
    bytes_per_second = effective_speed_mbps * 1_000_000 / 8
    
    # Calculate estimated time
    if bytes_per_second > 0:
        return file_size_bytes / bytes_per_second
    return 0


if __name__ == "__main__":
    import sys
    
    speed = get_wifi_speed()
    if speed:
        print(f"Network Speed: {speed} Mbps")
        print(f"Effective (90%): {float(speed) * 0.9:.1f} Mbps")
        
        chunk = calculate_optimal_chunk_size(float(speed))
        print(f"Optimal chunk size: {chunk // 1024} KB")
        
        # Example: estimate 1GB transfer
        gb_size = 1 * 1024 * 1024 * 1024
        time_sec = estimate_transfer_time_seconds(gb_size, float(speed))
        print(f"Estimated 1GB transfer time: {time_sec:.1f} seconds ({time_sec/60:.1f} minutes)")
    else:
        print("Could not detect network link speed", file=sys.stderr)
        sys.exit(1)
