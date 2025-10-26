#!/usr/bin/env python3
"""
udp_ssh_discover.py
Discover hosts via UDP probe then check for SSH (TCP/22) using TCP connect.
Usage:
    sudo python3 udp_ssh_discover.py --network 192.168.1.0/24
    OR
    python3 udp_ssh_discover.py --network 192.168.1.0/24  (if you've setcap cap_net_raw on python)
"""

import argparse
import ipaddress
import os
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Try to import scapy; fail with actionable message if not present
try:
    from scapy.all import IP, UDP, ICMP, sr, sr1, conf
except Exception as exc:
    sys.stderr.write(
        "Scapy import failed. Install scapy: pip install scapy\n"
        "Or on Arch: sudo pacman -S python-scapy\n"
    )
    raise

# Configuration defaults
DEFAULT_UDP_PORT = 161  # SNMP often elicits a reply or ICMP unreachable
UDP_PAYLOAD = b"whoami_probe"
UDP_TIMEOUT = 1.0  # seconds per packet batch
TCP_TIMEOUT = 1.5  # seconds for TCP connect
MAX_THREADS = 200   # threadpool size for TCP checks


def is_root_or_raw_allowed():
    """
    Return True if script has raw socket privileges (root or cap)
    We'll try to create a raw socket to test.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        s.close()
        return True
    except PermissionError:
        return False
    except Exception:
        # Other errors mean raw socket creation failed for other reasons,
        # treat as not allowed.
        return False


def expand_targets_from_network(network_cidr):
    """
    Expand a single IPv4 network CIDR into a list of host IPs (skip network & broadcast).
    """
    net = ipaddress.ip_network(network_cidr, strict=False)
    hosts = []
    for ip in net.hosts():
        hosts.append(str(ip))
    return hosts


def udp_discover(target_ips, udp_port=DEFAULT_UDP_PORT, timeout=UDP_TIMEOUT):
    """
    Send a UDP probe to each target IP's udp_port and capture replies (UDP or ICMP).
    Returns a set of IPs that responded or produced ICMP unreachable.
    This uses scapy's sr() in batches for efficiency.
    """
    discovered = set()
    # Scapy default verbosity off
    conf.verb = 0

    # Build list of packets
    packets = []
    for ip in target_ips:
        packet = IP(dst=ip) / UDP(dport=udp_port) / UDP_PAYLOAD
        packets.append(packet)

    # Send/receive
    # sr returns (answered, unanswered)
    try:
        answered, unanswered = sr(packets, timeout=timeout)
    except PermissionError as e:
        sys.stderr.write("PermissionError during sr(): need root or CAP_NET_RAW. Run with sudo or setcap.\n")
        raise

    # answered is list of tuples (sent, recv)
    for snd, rcv in answered:
        src = rcv.getlayer(IP).src
        # If we get any reply (UDP datagram back or ICMP), host is up
        discovered.add(src)

    # Additionally, scapy may not include ICMP port unreachable in answered for some setups,
    # but typically it does. For extra, analyze unanswered for ICMP (scapy-level may not include).
    # Return discovered set.
    return discovered


def tcp_check_port(ip, port=22, timeout=TCP_TIMEOUT, grab_banner=True):
    """
    Try a TCP connect to (ip, port). Return tuple (ip, port, open_bool, banner_or_error).
    """
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        banner = None
        if grab_banner:
            try:
                # set small recv timeout and attempt to receive banner
                sock.settimeout(0.8)
                banner_data = sock.recv(1024)
                if banner_data:
                    # decode best-effort
                    try:
                        banner = banner_data.decode('utf-8', errors='replace').strip()
                    except Exception:
                        banner = repr(banner_data)
            except socket.timeout:
                banner = None
        sock.close()
        return (ip, port, True, banner)
    except Exception as e:
        # port closed / filtered / unreachable
        if sock:
            try:
                sock.close()
            except Exception:
                pass
        return (ip, port, False, str(e))


def threaded_tcp_scan(ips, port=22, max_workers=MAX_THREADS):
    """
    Perform threaded TCP connect checks for each IP on the target port.
    Returns list of results (ip, port, is_open, banner_or_error).
    """
    results = []
    executor = ThreadPoolExecutor(max_workers=max_workers)
    future_to_ip = {}
    for ip in ips:
        future = executor.submit(tcp_check_port, ip, port)
        future_to_ip[future] = ip

    for future in as_completed(future_to_ip):
        try:
            res = future.result()
            results.append(res)
        except Exception as exc:
            ip = future_to_ip[future]
            results.append((ip, port, False, f"scan-error: {exc}"))

    executor.shutdown(wait=True)
    return results


def parse_args():
    parser = argparse.ArgumentParser(description="UDP discovery + SSH (TCP/22) port scanner")
    parser.add_argument("--network", "-n", required=True,
                        help="Target network in CIDR notation, e.g., 192.168.1.0/24")
    parser.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT,
                        help=f"UDP probe port (default {DEFAULT_UDP_PORT})")
    parser.add_argument("--timeout", type=float, default=UDP_TIMEOUT,
                        help="UDP probe timeout in seconds")
    parser.add_argument("--tcp-timeout", type=float, default=TCP_TIMEOUT,
                        help="TCP connect timeout in seconds")
    parser.add_argument("--no-udp", action="store_true",
                        help="Skip UDP discovery and directly scan all hosts with TCP connect")
    parser.add_argument("--workers", type=int, default=100,
                        help="Number of threads for TCP scanning (default 100)")
    parser.add_argument("--banner", action="store_true",
                        help="Try to capture SSH banner after connecting")
    return parser.parse_args()


def main():
    args = parse_args()

    # Update global timeouts from args
    global UDP_TIMEOUT, TCP_TIMEOUT, MAX_THREADS
    UDP_TIMEOUT = float(args.timeout)
    TCP_TIMEOUT = float(args.tcp_timeout)
    MAX_THREADS = int(args.workers)

    # Expand network to hosts
    try:
        targets = expand_targets_from_network(args.network)
    except Exception as e:
        sys.stderr.write("Invalid network CIDR: {}\n".format(e))
        sys.exit(1)

    print("Targets to consider: {} hosts".format(len(targets)))

    # Check raw privilege
    raw_ok = is_root_or_raw_allowed()
    if raw_ok:
        print("Raw socket allowed: UDP discovery will run.")
    else:
        print("Raw socket NOT allowed. UDP discovery will likely fail to capture ICMP. "
              "Either run with sudo or give CAP_NET_RAW to python. Proceeding...")

    discovered_hosts = set()

    if not args.no_udp:
        if raw_ok:
            print("Running UDP discovery on {} hosts (udp port {}) ...".format(len(targets), args.udp_port))
            start = time.time()
            try:
                discovered_hosts = udp_discover(targets, udp_port=args.udp_port, timeout=UDP_TIMEOUT)
            except Exception as e:
                sys.stderr.write("UDP discovery failed: {}\n".format(e))
                discovered_hosts = set()
            elapsed = time.time() - start
            print("UDP discovery finished in {:.2f}s: found {} hosts".format(elapsed, len(discovered_hosts)))
        else:
            print("Skipping UDP discovery due to lack of raw socket privileges.")
    else:
        print("User requested skip of UDP discovery (--no-udp).")

    # If no discovered hosts, fallback: scan whole network via TCP connect (slower, but works without root)
    if not discovered_hosts:
        print("No hosts discovered via UDP; falling back to TCP connect scan on all targets.")
        targets_to_scan = targets
    else:
        targets_to_scan = sorted(discovered_hosts)

    print("Starting TCP connect scan for SSH (port 22) on {} hosts ...".format(len(targets_to_scan)))
    tcp_results = threaded_tcp_scan(targets_to_scan, port=22, max_workers=MAX_THREADS)

    # Print results (only open ones)
    open_hosts = []
    for ip, port, is_open, info in tcp_results:
        if is_open:
            open_hosts.append((ip, port, info))

    if open_hosts:
        print("\nDiscovered SSH services (open port 22):")
        for ip, port, banner in open_hosts:
            if banner:
                print(f" - {ip}:{port}  banner: {banner}")
            else:
                print(f" - {ip}:{port}  banner: <none>")
    else:
        print("\nNo open SSH (port 22) found among scanned hosts.")

    # Optionally write results to file
    try:
        with open("ssh_scan_results.txt", "w") as fh:
            fh.write("Network scanned: {}\n".format(args.network))
            fh.write("SSH open hosts:\n")
            for ip, port, banner in open_hosts:
                fh.write(f"{ip}:{port}  {banner}\n")
        print("Saved results to ssh_scan_results.txt")
    except Exception:
        pass


if __name__ == "__main__":
    main()
