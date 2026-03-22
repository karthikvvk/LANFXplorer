"""
Link Speed Detection Utility

Detects the negotiated link speed of the WiFi or Ethernet interface on Linux or Windows.
Returns speed in Mbps which can be used for transfer time estimation.
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
    """Get link speed on Linux (tries WiFi first via iwconfig, then iw dev, then Ethernet)."""

    # Try WiFi first using iwconfig
    try:
        ip_out = run_cmd(["ip", "link", "show"])
        match = re.search(r"\d+:\s+(wlan\d+|wlp\w+|wl\w+):", ip_out)

        if match:
            iface = match.group(1)
            iwc_out = run_cmd(["iwconfig", iface])
            rate = re.search(r"Bit Rate[:=]\s*([\d.]+)\s*Mb/s", iwc_out)
            if rate:
                bitrate = float(rate.group(1))
                return {
                    "interface": iface,
                    "rx_mbps": bitrate,
                    "tx_mbps": bitrate,
                    "type": "wifi"
                }
    except Exception:
        pass

    # Second attempt: use `iw dev <iface> link`
    try:
        ip_out = run_cmd(["ip", "link", "show"])
        match = re.search(r"\d+:\s+(wlan\d+|wlp\w+|wl\w+):", ip_out)

        if match:
            iface = match.group(1)
            iw_out = run_cmd(["iw", "dev", iface, "link"])

            # Typical line: "tx bitrate: 72.2 MBit/s"
            rate = re.search(r"tx bitrate:\s*([\d.]+)\s*MBit/s", iw_out)
            if rate:
                bitrate = float(rate.group(1))
                return {
                    "interface": iface,
                    "rx_mbps": bitrate,
                    "tx_mbps": bitrate,
                    "type": "wifi"
                }
    except Exception:
        pass

    # Fallback: Ethernet via /sys/class/net
    try:
        import glob
        import os

        for sys_path in glob.glob("/sys/class/net/*"):
            iface = os.path.basename(sys_path)

            if iface == "lo" or iface.startswith(("wlan", "wlp", "wl")):
                continue

            operstate_path = os.path.join(sys_path, "operstate")
            if not os.path.exists(operstate_path):
                continue

            with open(operstate_path, "r") as f:
                state = f.read().strip()

            if state != "up" and state != "unknown":
                continue

            speed_path = os.path.join(sys_path, "speed")
            if os.path.exists(speed_path):
                try:
                    with open(speed_path, "r") as f:
                        speed_str = f.read().strip()
                        if speed_str and int(speed_str) > 0:
                            bitrate = float(speed_str)
                            return {
                                "interface": iface,
                                "rx_mbps": bitrate,
                                "tx_mbps": bitrate,
                                "type": "ethernet"
                            }
                except Exception:
                    continue
    except Exception:
        pass

    raise RuntimeError("No active network connection with detectable speed found")

def get_windows_link_speed():
    """Get link speed on Windows (tries WiFi first, then Ethernet)."""
    # Try WiFi first using netsh
    try:
        output = run_cmd(["netsh", "wlan", "show", "interfaces"])
        if "connected" in output.lower():
            rx = re.search(r"Receive rate \(Mbps\)\s*:\s*(\d+)", output)
            tx = re.search(r"Transmit rate \(Mbps\)\s*:\s*(\d+)", output)
            iface = re.search(r"Interface name\s*:\s*(.+)", output)

            if rx and tx:
                return {
                    "interface": iface.group(1).strip() if iface else "Wi-Fi",
                    "rx_mbps": float(rx.group(1)),
                    "tx_mbps": float(tx.group(1)),
                    "type": "wifi"
                }
    except Exception:
        pass
        
    # Ethernet Fallback: Use PowerShell to get active adapter speeds
    try:
        ps_cmd = 'Get-NetAdapter | Where-Object { $_.Status -eq "Up" } | Select-Object Name, LinkSpeed | ConvertTo-Json'
        output = run_cmd(["powershell", "-Command", ps_cmd])
        
        # Simple parse, avoiding json module to handle edge cases where output is not strict JSON
        import json
        try:
            adapters = json.loads(output)
            if not isinstance(adapters, list):
                adapters = [adapters]  # Only one adapter
                
            for adapter in adapters:
                if not adapter: continue
                speed_str = adapter.get("LinkSpeed", "")
                name = adapter.get("Name", "Ethernet")
                
                # LinkSpeed format is typically "1 Gbps" or "100 Mbps"
                match = re.search(r"(\d+(?:\.\d+)?)\s*(G|M|K)?bps", speed_str, re.IGNORECASE)
                if match:
                    val = float(match.group(1))
                    unit = match.group(2)
                    if unit and unit.upper() == "G":
                        val *= 1000  # Convert Gbps to Mbps
                    elif unit and unit.upper() == "K":
                        val /= 1000  # Convert Kbps to Mbps
                        
                    if val > 0:
                        return {
                            "interface": name,
                            "rx_mbps": val,
                            "tx_mbps": val,
                            "type": "ethernet"
                        }
        except Exception:
            pass
            
        # Optional WMI fallback if powershell fails
        wmic_out = run_cmd(["wmic", "nic", "where", "NetEnabled='true'", "get", "Name,Speed", "/format:csv"])
        lines = [line.strip() for line in wmic_out.splitlines() if line.strip() and "Node" not in line]
        for line in lines:
            parts = line.split(",")
            if len(parts) >= 3:
                 speed_bps = float(parts[-1])
                 name = parts[-2]
                 speed_mbps = speed_bps / 1000000
                 if speed_mbps > 0:
                     return {
                        "interface": name,
                        "rx_mbps": speed_mbps,
                        "tx_mbps": speed_mbps,
                        "type": "ethernet"
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


def calculate_optimal_chunk_size(speed_mbps: Optional[float] = None, file_size_bytes: Optional[int] = None) -> int:
    """
    Calculate optimal chunk size for file transfers based on negotiated link speed
    and (optionally) the file size.

    Larger chunks reduce per-chunk overhead and better utilise fast links.
    Smaller chunks keep memory usage low on slow connections.
    For large files (>500 MB) the chunk is doubled (up to 4 MB) to cut the
    number of read/send cycles significantly.

    Args:
        speed_mbps:      Negotiated link speed in Mbps, or None to auto-detect.
        file_size_bytes: Size of the file being transferred, or None to skip the
                         large-file adjustment.

    Returns:
        Chunk size in bytes.
    """
    if speed_mbps is None:
        val = get_wifi_speed()
        if val is None:
            return 64 * 1024
        speed = float(val)
    else:
        speed = float(speed_mbps)

    if speed <= 0.0:
        return 64 * 1024  # 64 KB fallback

    if speed <= 50.0:
        chunk = 64 * 1024        # 64 KB  — slow link
    elif speed <= 150.0:
        chunk = 512 * 1024       # 512 KB — standard WiFi (802.11n / 100 Mbps Ethernet)
    elif speed <= 500.0:
        chunk = 1024 * 1024      # 1 MB   — fast WiFi (802.11ac)
    else:
        chunk = 2 * 1024 * 1024  # 2 MB   — very fast WiFi / Ethernet

    # For large files (>500 MB) double the chunk to reduce overhead cycles.
    # Cap at 4 MB to avoid excessive memory pressure.
    if file_size_bytes and file_size_bytes > 500 * 1024 * 1024:
        chunk = min(chunk * 2, 4 * 1024 * 1024)

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
