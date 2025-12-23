"""
WiFi Speed Detection Utility

Detects the negotiated link speed of the WiFi interface on Linux or Windows.
Returns speed in Mbps which can be used for transfer time estimation.
"""
import platform
import subprocess
import re


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


def get_linux_wifi_speed():
    """Get WiFi speed on Linux using ip and iwconfig."""
    # Step 1: find wlan interface using ip
    ip_out = run_cmd(["ip", "link", "show"])
    match = re.search(r"\d+:\s+(wlan\d+|wlp\w+):", ip_out)

    if not match:
        raise RuntimeError("No wlan interface found")

    iface = match.group(1)

    # Step 2: query negotiated bitrate via iwconfig
    iwc_out = run_cmd(["iwconfig", iface])

    rate = re.search(r"Bit Rate[:=]\s*([\d.]+)\s*Mb/s", iwc_out)
    if not rate:
        raise RuntimeError("Bitrate not available (not connected?)")

    bitrate = float(rate.group(1))

    return {
        "interface": iface,
        "rx_mbps": bitrate,
        "tx_mbps": bitrate,
    }


def get_windows_wifi_speed():
    """Get WiFi speed on Windows using netsh."""
    output = run_cmd(["netsh", "wlan", "show", "interfaces"])

    if "connected" not in output.lower():
        raise RuntimeError("Wi-Fi not connected")

    rx = re.search(r"Receive rate \(Mbps\)\s*:\s*(\d+)", output)
    tx = re.search(r"Transmit rate \(Mbps\)\s*:\s*(\d+)", output)
    iface = re.search(r"Interface name\s*:\s*(.+)", output)

    if not rx or not tx:
        raise RuntimeError("Failed to parse negotiated rates")

    return {
        "interface": iface.group(1).strip() if iface else "Wi-Fi",
        "rx_mbps": float(rx.group(1)),
        "tx_mbps": float(tx.group(1)),
    }


def get_wifi_speed():
    """
    Get negotiated WiFi speed in Mbps.
    Returns None if WiFi speed cannot be determined.
    """
    os_type = platform.system()
    
    try:
        if os_type == "Linux":
            info = get_linux_wifi_speed()
        elif os_type == "Windows":
            info = get_windows_wifi_speed()
        else:
            return None
        
        # Return the lower of rx/tx as conservative estimate
        return min(info["rx_mbps"], info["tx_mbps"])
    except Exception as e:
        print(f"[wifi_speed] Could not detect WiFi speed: {e}")
        return None


def estimate_transfer_time_seconds(file_size_bytes: int, speed_mbps: float = None) -> float:
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
        speed_mbps = get_wifi_speed()
    
    if speed_mbps is None or speed_mbps <= 0:
        return 0
    
    # Use 90% of negotiated speed (10% reduction for overhead/real-world)
    effective_speed_mbps = speed_mbps * 0.9
    
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
        print(f"WiFi Speed: {speed} Mbps")
        print(f"Effective (90%): {speed * 0.9:.1f} Mbps")
        
        # Example: estimate 1GB transfer
        gb_size = 1 * 1024 * 1024 * 1024
        time_sec = estimate_transfer_time_seconds(gb_size, speed)
        print(f"Estimated 1GB transfer time: {time_sec:.1f} seconds ({time_sec/60:.1f} minutes)")
    else:
        print("Could not detect WiFi speed", file=sys.stderr)
        sys.exit(1)
