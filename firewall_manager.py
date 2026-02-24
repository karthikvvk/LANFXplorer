#!/usr/bin/env python3
"""
LANFXplorer Firewall Manager

Cross-platform firewall handling with two modes:

1. PRIVILEGED (install-time):
   Adds allow rules for all required ports via the system firewall backend.
   - Linux: auto-detects ufw / firewalld / nftables / iptables
   - Windows: uses netsh advfirewall

2. NON-PRIVILEGED (every-launch):
   Probes all required ports by attempting bind() to verify they are locally
   available.  Warns the user if any port cannot be bound.

Usage:
    python firewall_manager.py --install   # privileged: add firewall rules
    python firewall_manager.py --probe     # non-privileged: check port availability
    python firewall_manager.py --remove    # privileged: remove LANFXplorer rules

Programmatic:
    from firewall_manager import ensure_firewall_rules, probe_ports
    ensure_firewall_rules()   # call during install
    probe_ports()             # call on every launch
"""

import os
import sys
import socket
import platform
import subprocess
import shutil
from pathlib import Path
from typing import List, Tuple, Optional

# Ensure we can import app_config even when run standalone
sys.path.insert(0, str(Path(__file__).parent.resolve()))
from app_config import AppConfig


# ──────────────────────────────────────────────────────────────
# Port registry
# ──────────────────────────────────────────────────────────────
RULE_TAG = "LANFXplorer"

# (port, protocol, description, expose_to_network)
# expose_to_network=False → localhost-only, no firewall rule needed
REQUIRED_PORTS: List[Tuple[int, str, str, bool]] = [
    (AppConfig.QUIC_PORT,           "udp", "QUIC File Transfer",  True),
    (AppConfig.CA_DISCOVERY_PORT,   "udp", "CA Discovery",        True),
    (AppConfig.CA_SIGNING_PORT,     "tcp", "CA Signing",          True),
    (AppConfig.PEER_DISCOVERY_PORT, "udp", "Peer Discovery",      True),
    (AppConfig.HANDSHAKE_PORT,      "tcp", "Handshake Service",   True),
    (AppConfig.API_PORT,            "tcp", "Flask API (local)",    False),
]


def _print(symbol: str, msg: str) -> None:
    print(f"[{symbol}] {msg}")


# ╔══════════════════════════════════════════════════════════════╗
# ║  NON-PRIVILEGED: Port probe (every launch)                  ║
# ╚══════════════════════════════════════════════════════════════╝

def probe_ports() -> List[Tuple[int, str, str, str]]:
    """
    Attempt to bind() to each required port to verify local availability.

    Returns a list of (port, protocol, status, message) tuples.
    status is one of: 'ok', 'in_use', 'error'.

    This does NOT require elevated privileges.
    """
    results: List[Tuple[int, str, str, str]] = []

    for port, proto, desc, _expose in REQUIRED_PORTS:
        sock_type = socket.SOCK_DGRAM if proto == "udp" else socket.SOCK_STREAM
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, sock_type)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # SO_REUSEPORT on Linux allows multiple binds; we just want availability
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            sock.bind(("0.0.0.0", port))
            results.append((port, proto, "ok", f"{desc} — port {port}/{proto} available"))
        except OSError as exc:
            if exc.errno in (98, 10048):  # EADDRINUSE (Linux 98, Windows 10048)
                results.append((port, proto, "in_use",
                                f"{desc} — port {port}/{proto} already in use"))
            else:
                results.append((port, proto, "error",
                                f"{desc} — port {port}/{proto} error: {exc}"))
        finally:
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass

    # ── Print summary ──
    _print("ℹ", "Firewall port-probe results:")
    blocked = []
    for port, proto, status, msg in results:
        if status == "ok":
            _print("✓", msg)
        elif status == "in_use":
            _print("⚠", msg)
        else:
            _print("✗", msg)
            blocked.append((port, proto, msg))

    if blocked:
        _print("⚠", "Some ports could not be bound.  If you have not yet run the "
                     "installer, run:  sudo python3 firewall_manager.py --install")

    return results


# ╔══════════════════════════════════════════════════════════════╗
# ║  PRIVILEGED: Firewall rule management (install-time)         ║
# ╚══════════════════════════════════════════════════════════════╝

# ── Helpers to detect Linux firewall backend ──

def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(args: List[str], check: bool = False, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=15, check=check, **kw)


def _detect_linux_backend() -> Optional[str]:
    """
    Return the first *active* firewall backend found, in priority order.
    Returns one of: 'ufw', 'firewalld', 'nftables', 'iptables', or None.
    """
    # ufw
    if _has("ufw"):
        r = _run(["ufw", "status"])
        if r.returncode == 0 and "active" in r.stdout.lower():
            return "ufw"

    # firewalld
    if _has("firewall-cmd"):
        r = _run(["firewall-cmd", "--state"])
        if r.returncode == 0 and "running" in r.stdout.lower():
            return "firewalld"

    # nftables (check if nft binary exists AND has rulesets loaded)
    if _has("nft"):
        r = _run(["nft", "list", "ruleset"])
        if r.returncode == 0 and r.stdout.strip():
            return "nftables"

    # iptables (always last-resort; almost always present)
    if _has("iptables"):
        return "iptables"

    return None


# ── Linux: ufw ──

def _ufw_rule_exists(port: int, proto: str) -> bool:
    r = _run(["ufw", "status", "numbered"])
    if r.returncode != 0:
        return False
    marker = f"{port}/{proto}"
    return marker in r.stdout and RULE_TAG in r.stdout

def _ufw_add(port: int, proto: str, desc: str) -> None:
    if _ufw_rule_exists(port, proto):
        _print("✓", f"ufw: rule already exists for {port}/{proto}")
        return
    r = _run(["ufw", "allow", f"{port}/{proto}", "comment", f"{RULE_TAG} {desc}"])
    if r.returncode == 0:
        _print("✓", f"ufw: allowed {port}/{proto} ({desc})")
    else:
        _print("✗", f"ufw: failed to add {port}/{proto}: {r.stderr.strip()}")

def _ufw_remove(port: int, proto: str) -> None:
    _run(["ufw", "delete", "allow", f"{port}/{proto}"])


# ── Linux: firewalld ──

def _firewalld_rule_exists(port: int, proto: str) -> bool:
    r = _run(["firewall-cmd", "--query-port", f"{port}/{proto}"])
    return r.returncode == 0

def _firewalld_add(port: int, proto: str, desc: str) -> None:
    if _firewalld_rule_exists(port, proto):
        _print("✓", f"firewalld: rule already exists for {port}/{proto}")
        return
    r = _run(["firewall-cmd", "--permanent", "--add-port", f"{port}/{proto}"])
    if r.returncode == 0:
        _print("✓", f"firewalld: allowed {port}/{proto} ({desc})")
    else:
        _print("✗", f"firewalld: failed: {r.stderr.strip()}")

def _firewalld_remove(port: int, proto: str) -> None:
    _run(["firewall-cmd", "--permanent", "--remove-port", f"{port}/{proto}"])

def _firewalld_reload() -> None:
    _run(["firewall-cmd", "--reload"])


# ── Linux: nftables ──

_NFT_TABLE = f"inet {RULE_TAG}"

def _nft_table_exists() -> bool:
    r = _run(["nft", "list", "tables"])
    return RULE_TAG in (r.stdout or "")

def _nft_rule_exists(port: int, proto: str) -> bool:
    r = _run(["nft", "list", "table", "inet", RULE_TAG])
    if r.returncode != 0:
        return False
    return f"{proto} dport {port}" in r.stdout

def _nft_ensure_table() -> None:
    """Create the LANFXplorer nft table + chain if missing."""
    if _nft_table_exists():
        return
    cmds = [
        ["nft", "add", "table", "inet", RULE_TAG],
        ["nft", "add", "chain", "inet", RULE_TAG, "input",
         "{ type filter hook input priority 0 ; policy accept ; }"],
    ]
    for cmd in cmds:
        r = _run(cmd)
        if r.returncode != 0:
            _print("✗", f"nft: {' '.join(cmd)} → {r.stderr.strip()}")

def _nft_add(port: int, proto: str, desc: str) -> None:
    _nft_ensure_table()
    if _nft_rule_exists(port, proto):
        _print("✓", f"nft: rule already exists for {port}/{proto}")
        return
    r = _run(["nft", "add", "rule", "inet", RULE_TAG, "input",
              proto, "dport", str(port), "accept",
              "comment", f'"{RULE_TAG} {desc}"'])
    if r.returncode == 0:
        _print("✓", f"nft: allowed {port}/{proto} ({desc})")
    else:
        _print("✗", f"nft: failed: {r.stderr.strip()}")

def _nft_remove_all() -> None:
    if _nft_table_exists():
        _run(["nft", "delete", "table", "inet", RULE_TAG])
        _print("✓", "nft: removed LANFXplorer table")


# ── Linux: iptables ──

def _iptables_rule_exists(port: int, proto: str) -> bool:
    r = _run(["iptables-save"])
    if r.returncode != 0:
        return False
    # Look for our tagged rule
    needle = f"--dport {port} -j ACCEPT -m comment --comment \"{RULE_TAG}"
    return needle in r.stdout

def _iptables_add(port: int, proto: str, desc: str) -> None:
    if _iptables_rule_exists(port, proto):
        _print("✓", f"iptables: rule already exists for {port}/{proto}")
        return
    r = _run([
        "iptables", "-A", "INPUT",
        "-p", proto, "--dport", str(port),
        "-j", "ACCEPT",
        "-m", "comment", "--comment", f"{RULE_TAG} {desc}",
    ])
    if r.returncode == 0:
        _print("✓", f"iptables: allowed {port}/{proto} ({desc})")
    else:
        _print("✗", f"iptables: failed: {r.stderr.strip()}")

def _iptables_remove(port: int, proto: str, desc: str) -> None:
    _run([
        "iptables", "-D", "INPUT",
        "-p", proto, "--dport", str(port),
        "-j", "ACCEPT",
        "-m", "comment", "--comment", f"{RULE_TAG} {desc}",
    ])


# ── Windows: netsh ──

def _netsh_rule_name(port: int, proto: str, direction: str) -> str:
    return f"{RULE_TAG}_{proto.upper()}_{port}_{direction.upper()}"

def _netsh_rule_exists(port: int, proto: str, direction: str) -> bool:
    name = _netsh_rule_name(port, proto, direction)
    r = _run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"])
    return r.returncode == 0 and name in (r.stdout or "")

def _netsh_add(port: int, proto: str, desc: str) -> None:
    for direction in ("in", "out"):
        if _netsh_rule_exists(port, proto, direction):
            _print("✓", f"netsh: rule already exists for {port}/{proto} {direction}")
            continue
        name = _netsh_rule_name(port, proto, direction)
        r = _run([
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={name}",
            f"dir={direction}",
            "action=allow",
            f"protocol={proto}",
            f"localport={port}",
            f"description={RULE_TAG}: {desc}",
        ])
        if r.returncode == 0:
            _print("✓", f"netsh: allowed {port}/{proto} {direction} ({desc})")
        else:
            _print("✗", f"netsh: failed {port}/{proto} {direction}: {r.stderr.strip()}")

def _netsh_remove(port: int, proto: str) -> None:
    for direction in ("in", "out"):
        name = _netsh_rule_name(port, proto, direction)
        _run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={name}"])


# ╔══════════════════════════════════════════════════════════════╗
# ║  Public API                                                  ║
# ╚══════════════════════════════════════════════════════════════╝

def ensure_firewall_rules() -> bool:
    """
    Add firewall allow rules for all required ports (PRIVILEGED).

    Returns True if all rules were applied successfully, False otherwise.
    """
    system = platform.system().lower()
    network_ports = [(p, pr, d) for p, pr, d, expose in REQUIRED_PORTS if expose]

    if system == "windows":
        _print("ℹ", "Configuring Windows Firewall via netsh...")
        for port, proto, desc in network_ports:
            _netsh_add(port, proto, desc)
        return True

    # ── Linux / Unix ──
    backend = _detect_linux_backend()
    if backend is None:
        _print("⚠", "No active firewall detected.  Skipping rule creation.")
        _print("ℹ", "If you have a firewall, manually allow ports: "
                     + ", ".join(f"{p}/{pr}" for p, pr, _, e in REQUIRED_PORTS if e))
        return True  # Not an error — just no firewall to configure

    _print("ℹ", f"Detected firewall backend: {backend}")

    if backend == "ufw":
        for port, proto, desc in network_ports:
            _ufw_add(port, proto, desc)

    elif backend == "firewalld":
        for port, proto, desc in network_ports:
            _firewalld_add(port, proto, desc)
        _firewalld_reload()

    elif backend == "nftables":
        for port, proto, desc in network_ports:
            _nft_add(port, proto, desc)

    elif backend == "iptables":
        for port, proto, desc in network_ports:
            _iptables_add(port, proto, desc)

    _print("✓", "Firewall rules configured for LANFXplorer")
    return True


def remove_firewall_rules() -> None:
    """
    Remove all LANFXplorer firewall rules (PRIVILEGED).
    """
    system = platform.system().lower()
    network_ports = [(p, pr, d) for p, pr, d, expose in REQUIRED_PORTS if expose]

    if system == "windows":
        for port, proto, desc in network_ports:
            _netsh_remove(port, proto)
        _print("✓", "Removed all LANFXplorer Windows Firewall rules")
        return

    backend = _detect_linux_backend()
    if backend is None:
        _print("⚠", "No active firewall detected.  Nothing to remove.")
        return

    _print("ℹ", f"Removing rules via {backend}...")

    if backend == "ufw":
        for port, proto, desc in network_ports:
            _ufw_remove(port, proto)

    elif backend == "firewalld":
        for port, proto, desc in network_ports:
            _firewalld_remove(port, proto)
        _firewalld_reload()

    elif backend == "nftables":
        _nft_remove_all()

    elif backend == "iptables":
        for port, proto, desc in network_ports:
            _iptables_remove(port, proto, desc)

    _print("✓", "Removed all LANFXplorer firewall rules")


# ╔══════════════════════════════════════════════════════════════╗
# ║  CLI entry-point                                             ║
# ╚══════════════════════════════════════════════════════════════╝

def _cli_help():
    print("Usage: python firewall_manager.py [--install | --probe | --remove | --help]")
    print()
    print("  --install   Add firewall rules for LANFXplorer ports (requires privileges)")
    print("  --probe     Check if required ports are locally bindable (no privileges)")
    print("  --remove    Remove LANFXplorer firewall rules (requires privileges)")
    print("  --help      Show this help")
    print()
    print("Required ports:")
    for port, proto, desc, expose in REQUIRED_PORTS:
        scope = "network" if expose else "localhost"
        print(f"  {port:>5}/{proto:<3}  {desc:<30}  [{scope}]")


if __name__ == "__main__":
    if len(sys.argv) < 2 or "--help" in sys.argv:
        _cli_help()
        sys.exit(0)

    action = sys.argv[1]

    if action == "--install":
        success = ensure_firewall_rules()
        sys.exit(0 if success else 1)

    elif action == "--probe":
        results = probe_ports()
        # Exit 1 if any port had an error (not just in_use)
        errors = [r for r in results if r[2] == "error"]
        sys.exit(1 if errors else 0)

    elif action == "--remove":
        remove_firewall_rules()
        sys.exit(0)

    else:
        print(f"Unknown action: {action}")
        _cli_help()
        sys.exit(1)
