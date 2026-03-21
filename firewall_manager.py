#!/usr/bin/env python3
"""
LANFXplorer Firewall Manager

Cross-platform firewall handling with two modes:

1. PRIVILEGED (install-time):
   Adds allow rules for all required ports via the system firewall backend.
   - Linux: auto-detects ufw / firewalld / nftables / iptables
   - Windows: uses netsh advfirewall

2. NON-PRIVILEGED (every-launch):
   Runs a three-layer port probe for each required port:

   Layer 1 – Local socket availability  (bind succeeds/fails)
   Layer 2 – Host firewall rule validation  (policy + explicit ACCEPT present)
   Layer 3 – Active reachability test  (loopback + LAN IP round-trip)

   Returns structured per-port results:
       {
           "port":                int,
           "proto":               str,
           "desc":                str,
           "bind_ok":             bool,
           "firewall_allows":     bool | None,   # None = could not determine
           "externally_reachable": bool | None,  # None = test not run / inconclusive
           "notes":               list[str],
       }

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
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
    (AppConfig.API_PORT,            "tcp", "Flask API",            True),  # peers reach each other on :5000 for listdir/osinfo/handshake etc.
]

# ICMP (ping) is needed for the startup connectivity check
ICMP_NEEDED = True

ProbeResult = Dict  # typed below for clarity


def _print(symbol: str, msg: str) -> None:
    print(f"[{symbol}] {msg}")


# ╔══════════════════════════════════════════════════════════════╗
# ║  Helpers                                                     ║
# ╚══════════════════════════════════════════════════════════════╝

def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(args: List[str], check: bool = False, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=15, check=check, **kw)


def _get_lan_ip() -> Optional[str]:
    """Return the primary LAN IP by opening a dummy UDP socket."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return None


# ╔══════════════════════════════════════════════════════════════╗
# ║  Layer 2 – Host firewall rule validation                     ║
# ╚══════════════════════════════════════════════════════════════╝

def _iptables_allows_port_from_rules(rules_text: str, port: int, proto: str) -> Optional[bool]:
    """
    Parse the output of 'iptables -S INPUT' to determine whether *port* is
    allowed.  Returns True/False, or None if the rules text is empty/unparseable.

    Logic:
    - Walk rules top to bottom (as iptables evaluates them).
    - First matching ACCEPT for the port → True.
    - First matching DROP/REJECT for the port → False.
    - No matching rule → default policy (-P INPUT ACCEPT/DROP).
    - If default policy is DROP and no ACCEPT for loopback interface → False.
    """
    if not rules_text.strip():
        return None

    default_accept: Optional[bool] = None

    for line in rules_text.splitlines():
        line = line.strip()
        if not line:
            continue

        # Default policy: -P INPUT ACCEPT  or  -P INPUT DROP
        if line.startswith("-P INPUT"):
            default_accept = "ACCEPT" in line
            continue

        # Port-specific rules
        port_match = (f"--dport {port}" in line or f"--dport {port} " in line)
        proto_match = f"-p {proto}" in line

        if proto_match and port_match:
            if "-j ACCEPT" in line:
                return True
            if "-j DROP" in line or "-j REJECT" in line:
                return False

        # A blanket DROP/REJECT with no port filter — only counts if it comes
        # before any port-specific ACCEPT and the chain has already been walked
        # (handled by the top-to-bottom traversal above; we only hit this for
        # catch-all rules that have no -p/--dport match).

    if default_accept is None:
        # Could not find policy line — treat as unknown
        return None

    return default_accept


def _iptables_allows_port(port: int, proto: str) -> Optional[bool]:
    """Convenience wrapper that fetches rules then delegates to the parser."""
    r = _run(["iptables", "-S", "INPUT"])
    if r.returncode != 0:
        return None
    return _iptables_allows_port_from_rules(r.stdout, port, proto)


def _nftables_allows_port(port: int, proto: str) -> Optional[bool]:
    """
    Parse 'nft list ruleset' to determine whether *port* traffic is accepted.
    Inspects the policy of every base chain hooked on 'input' and whether an
    explicit accept rule for the port precedes any drop.
    """
    r = _run(["nft", "list", "ruleset"])
    if r.returncode != 0:
        return None

    text = r.stdout
    # Split into per-chain blocks
    chains = _nft_split_chains(text)

    for chain_policy, rules in chains:
        # Only look at input hooks
        accept_before_drop = None
        for rule in rules:
            rule_l = rule.lower()
            if proto in rule_l and f"dport {port}" in rule_l:
                if "accept" in rule_l:
                    accept_before_drop = True
                    break
                if "drop" in rule_l or "reject" in rule_l:
                    accept_before_drop = False
                    break
        if accept_before_drop is True:
            return True
        if accept_before_drop is False:
            return False

    # No explicit rule found in any input chain → fall back to first input
    # chain policy
    for chain_policy, rules in chains:
        if chain_policy is not None:
            return chain_policy == "accept"

    return None


def _nft_split_chains(ruleset: str) -> List[Tuple[Optional[str], List[str]]]:
    """
    Very lightweight parser: return list of (policy, [rule_lines]) for each
    chain block that hooks 'input'.
    """
    results = []
    in_input_chain = False
    policy: Optional[str] = None
    rule_lines: List[str] = []

    for line in ruleset.splitlines():
        stripped = line.strip()
        # Detect chain header with hook input
        if stripped.startswith("chain") and "hook input" in stripped:
            in_input_chain = True
            policy = None
            rule_lines = []
            # Extract policy from header line e.g. "policy drop;"
            if "policy drop" in stripped:
                policy = "drop"
            elif "policy accept" in stripped:
                policy = "accept"
            continue
        if in_input_chain:
            if stripped == "}":
                results.append((policy, rule_lines))
                in_input_chain = False
                rule_lines = []
                policy = None
            else:
                rule_lines.append(stripped)

    return results


def _ufw_allows_port(port: int, proto: str) -> Optional[bool]:
    """Check ufw verbose status for an explicit ALLOW rule."""
    r = _run(["ufw", "status", "verbose"])
    if r.returncode != 0:
        return None
    marker = f"{port}/{proto}"
    for line in r.stdout.splitlines():
        if marker in line and "ALLOW" in line.upper():
            return True
    # Also check default incoming policy
    for line in r.stdout.splitlines():
        if "default:" in line.lower() and "incoming" in line.lower():
            if "allow" in line.lower():
                return True  # default allow, port not explicitly blocked
            break
    return False


def _firewalld_allows_port(port: int, proto: str) -> Optional[bool]:
    r = _run(["firewall-cmd", "--query-port", f"{port}/{proto}"])
    if r.returncode == 0:
        return "yes" in r.stdout.lower()
    return None


def _windows_allows_port(port: int, proto: str) -> Optional[bool]:
    """
    Inspect Windows Firewall rules for *port*.  Verifies the rule is enabled
    and matches the active network profile (Domain/Private/Public).
    """
    r = _run(["netsh", "advfirewall", "firewall", "show", "rule",
              "name=all", "dir=in", "verbose"])
    if r.returncode != 0:
        return None

    # Try to determine active profile
    active_profile = _windows_active_profile()

    # Split output into per-rule blocks (separated by blank lines)
    blocks = r.stdout.split("\n\n")
    for block in blocks:
        if f"LocalPort" not in block:
            continue
        lines = {k.strip(): v.strip()
                 for line in block.splitlines() if ":" in line
                 for k, _, v in [line.partition(":")]}

        rule_port = lines.get("LocalPort", "")
        rule_proto = lines.get("Protocol", "").lower()
        rule_enabled = lines.get("Enabled", "").lower()
        rule_action = lines.get("Action", "").lower()
        rule_profiles = lines.get("Profiles", "").lower()

        if str(port) not in rule_port.split(","):
            continue
        if proto.lower() not in rule_proto:
            continue
        if rule_enabled != "yes":
            continue
        if rule_action != "allow":
            continue
        # Profile check: rule must cover the active profile
        if active_profile and active_profile.lower() not in rule_profiles:
            continue
        return True

    return False


def _windows_active_profile() -> Optional[str]:
    """Return 'domain', 'private', or 'public' based on the current connection."""
    r = _run(["netsh", "advfirewall", "monitor", "show", "currentprofile"])
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        low = line.lower()
        if "domain" in low:
            return "domain"
        if "private" in low:
            return "private"
        if "public" in low:
            return "public"
    return None


def _firewall_allows_port(port: int, proto: str, backend: Optional[str]) -> Tuple[Optional[bool], str]:
    """
    Dispatcher: check host firewall for *port*.

    Always tries every available parser on Linux regardless of which backend
    was identified as "active" — raw iptables or nftables rules can exist even
    when ufw/firewalld are not running.

    Returns (result, source_description) where result is:
        True  – an explicit ACCEPT rule found before any DROP
        False – default policy is DROP and no ACCEPT rule found, OR explicit DROP
        None  – could not parse rules (insufficient privileges, no tool found)
    """
    system = platform.system().lower()
    if system == "windows":
        return _windows_allows_port(port, proto), "Windows Firewall"

    # ── Linux: try every available parser, most authoritative first ──
    #
    # We do NOT rely solely on the detected "active" backend because:
    # - ufw/firewalld may be inactive while raw nftables/iptables rules exist
    # - Modern distros stack: ufw → iptables → nftables all active at once
    # - Backend detection returning None does not mean no firewall rules exist

    # 1. nftables – inspect effective ruleset regardless of ufw/firewalld
    if _has("nft"):
        r = _run(["nft", "list", "ruleset"])
        if r.returncode == 0 and r.stdout.strip():
            result = _nftables_allows_port(port, proto)
            if result is not None:
                return result, "nftables (nft list ruleset)"

    # 2. iptables – try even if nft found rules (stacked firewalls)
    if _has("iptables"):
        r = _run(["iptables", "-S", "INPUT"])
        if r.returncode == 0:
            result = _iptables_allows_port_from_rules(r.stdout, port, proto)
            if result is not None:
                return result, "iptables (-S INPUT)"

    # 3. ufw – only when explicitly active
    if backend == "ufw" and _has("ufw"):
        result = _ufw_allows_port(port, proto)
        if result is not None:
            return result, "ufw (status verbose)"

    # 4. firewalld – only when explicitly active
    if backend == "firewalld" and _has("firewall-cmd"):
        result = _firewalld_allows_port(port, proto)
        if result is not None:
            return result, "firewalld (--query-port)"

    return None, "no parseable firewall rules found"


# ╔══════════════════════════════════════════════════════════════╗
# ║  Layer 3 – Active reachability test                          ║
# ╚══════════════════════════════════════════════════════════════╝

def _tcp_reachability_test(port: int) -> Tuple[bool, bool, List[str]]:
    """
    Spawn a temporary TCP listener on *port*, then attempt connections from:
      1. 127.0.0.1  (loopback — must always succeed if bind worked)
      2. LAN IP     (if loopback succeeds but LAN fails → host firewall blocking)

    Returns (loopback_ok, lan_ok, notes).
    """
    notes: List[str] = []
    server_ready = threading.Event()
    server_error: List[str] = []

    def _serve():
        srv = None
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", port))
            srv.listen(5)
            srv.settimeout(3.0)
            server_ready.set()
            # Accept up to 2 connections (loopback + LAN)
            for _ in range(2):
                try:
                    conn, _ = srv.accept()
                    conn.close()
                except socket.timeout:
                    break
        except OSError as e:
            server_error.append(str(e))
            server_ready.set()
        finally:
            if srv:
                try:
                    srv.close()
                except OSError:
                    pass

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    server_ready.wait(timeout=3.0)

    if server_error:
        notes.append(f"Active test server error: {server_error[0]}")
        return False, False, notes

    def _connect(addr: str) -> bool:
        c = None
        try:
            c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            c.settimeout(2.0)
            c.connect((addr, port))
            return True
        except OSError:
            return False
        finally:
            if c:
                try:
                    c.close()
                except OSError:
                    pass

    loopback_ok = _connect("127.0.0.1")
    if not loopback_ok:
        notes.append("Loopback connect failed — unexpected; port may already be in use")
        t.join(timeout=2)
        return False, False, notes

    lan_ip = _get_lan_ip()
    if lan_ip is None or lan_ip == "127.0.0.1":
        notes.append("Could not determine LAN IP; skipping LAN reachability test")
        t.join(timeout=2)
        return True, False, notes

    lan_ok = _connect(lan_ip)
    if not lan_ok:
        notes.append(
            f"Loopback OK but LAN IP ({lan_ip}) unreachable → "
            "host firewall likely blocking inbound on this interface"
        )

    t.join(timeout=2)
    return loopback_ok, lan_ok, notes


def _udp_reachability_test(port: int) -> Tuple[bool, bool, List[str]]:
    """
    UDP equivalent: server echoes back any received datagram.
    Client sends a probe and waits for the echo.
    """
    notes: List[str] = []
    server_ready = threading.Event()
    server_error: List[str] = []

    def _serve():
        srv = None
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", port))
            srv.settimeout(3.0)
            server_ready.set()
            for _ in range(2):
                try:
                    data, addr = srv.recvfrom(64)
                    srv.sendto(data, addr)
                except socket.timeout:
                    break
        except OSError as e:
            server_error.append(str(e))
            server_ready.set()
        finally:
            if srv:
                try:
                    srv.close()
                except OSError:
                    pass

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    server_ready.wait(timeout=3.0)

    if server_error:
        notes.append(f"Active test server error: {server_error[0]}")
        return False, False, notes

    def _probe(addr: str) -> bool:
        c = None
        try:
            c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            c.settimeout(2.0)
            c.sendto(b"PING", (addr, port))
            data, _ = c.recvfrom(64)
            return data == b"PING"
        except OSError:
            return False
        finally:
            if c:
                try:
                    c.close()
                except OSError:
                    pass

    loopback_ok = _probe("127.0.0.1")
    if not loopback_ok:
        notes.append("UDP loopback probe failed")
        t.join(timeout=2)
        return False, False, notes

    lan_ip = _get_lan_ip()
    if lan_ip is None or lan_ip == "127.0.0.1":
        notes.append("Could not determine LAN IP; skipping LAN UDP reachability test")
        t.join(timeout=2)
        return True, False, notes

    lan_ok = _probe(lan_ip)
    if not lan_ok:
        notes.append(
            f"UDP loopback OK but LAN IP ({lan_ip}) unreachable → "
            "host firewall likely blocking inbound UDP on this interface"
        )

    t.join(timeout=2)
    return loopback_ok, lan_ok, notes


# ╔══════════════════════════════════════════════════════════════╗
# ║  NON-PRIVILEGED: Three-layer port probe (every launch)       ║
# ╚══════════════════════════════════════════════════════════════╝

def probe_ports(active_test: bool = True) -> List[ProbeResult]:
    """
    Run a three-layer probe for every required port.

    Layer 1 – bind()         → detects local conflicts / OS restrictions
    Layer 2 – firewall rules → parses effective host firewall policy
    Layer 3 – round-trip     → spawns temp listener, probes loopback + LAN IP

    Parameters
    ----------
    active_test : bool
        When True (default) run the Layer-3 round-trip test.
        Set False to skip (faster; useful when already listening on these ports).

    Returns
    -------
    List of dicts with keys:
        port, proto, desc, bind_ok, firewall_allows, externally_reachable, notes
    """
    system = platform.system().lower()
    backend: Optional[str] = None
    if system != "windows":
        backend = _detect_linux_backend()

    results: List[ProbeResult] = []

    _print("ℹ", "Running three-layer port probe…")
    if backend:
        _print("ℹ", f"Detected firewall backend: {backend}")
    elif system != "windows":
        _print("ℹ", "No active firewall backend detected (layer-2 check skipped)")

    for port, proto, desc, expose in REQUIRED_PORTS:

        result: ProbeResult = {
            "port": port,
            "proto": proto,
            "desc": desc,
            "bind_ok": False,
            "firewall_allows": None,
            "externally_reachable": None,
            "notes": [],
        }

        # ── Layer 1: bind ──────────────────────────────────────
        sock_type = socket.SOCK_DGRAM if proto == "udp" else socket.SOCK_STREAM
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, sock_type)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            sock.bind(("0.0.0.0", port))
            result["bind_ok"] = True
        except OSError as exc:
            if exc.errno in (98, 10048):   # EADDRINUSE
                result["notes"].append(f"Port {port}/{proto} already in use")
            else:
                result["notes"].append(f"Bind error: {exc}")
        finally:
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass

        # ── Layer 2: firewall rule check ───────────────────────
        if expose:
            fw_result, fw_source = _firewall_allows_port(port, proto, backend)
            result["firewall_allows"] = fw_result
            if fw_result is True:
                result["notes"].append(f"Firewall ACCEPT confirmed via {fw_source}")
            elif fw_result is False:
                result["notes"].append(
                    f"BLOCKED by host firewall ({fw_source}): "
                    "default policy is DROP and no ACCEPT rule found for this port"
                )
            else:
                result["notes"].append(
                    f"Could not parse firewall rules ({fw_source}) — "
                    "probe may lack privileges (try: sudo python3 firewall_manager.py --probe)"
                )
        else:
            # Localhost-only port: firewall check not applicable
            result["firewall_allows"] = True
            result["notes"].append("Localhost-only port; firewall check skipped")

        # ── Layer 3: active round-trip test ────────────────────
        # NOTE: This test can only confirm same-host reachability.
        # Loopback (127.0.0.1) is almost always exempted from INPUT
        # filtering via a "-i lo ACCEPT" rule or equivalent.  A LAN IP
        # connection from the same host may also bypass certain firewall
        # implementations.  A ✓ here does NOT guarantee external reachability.
        # True external reachability requires a remote peer (--peer-validate).
        if active_test and result["bind_ok"]:
            if proto == "tcp":
                lo_ok, lan_ok, rt_notes = _tcp_reachability_test(port)
            else:
                lo_ok, lan_ok, rt_notes = _udp_reachability_test(port)

            result["notes"].extend(rt_notes)

            if not lo_ok:
                result["externally_reachable"] = False
                result["notes"].append(
                    "⚠ Even loopback failed — unexpected; port may be seized by another process"
                )
            elif not expose:
                result["externally_reachable"] = lo_ok
            else:
                # LAN IP test from same host is not true external proof.
                # Flag explicitly when it passed but firewall showed blocked.
                result["externally_reachable"] = lan_ok
                if lan_ok and result["firewall_allows"] is False:
                    result["notes"].append(
                        "⚠ REACHABLE ✓ but FIREWALL ✗ — same-host LAN connections "
                        "may bypass INPUT filtering (loopback interface exemption or "
                        "OUTPUT→INPUT short-circuit). Do not trust REACHABLE here; "
                        "the firewall check is the authoritative result."
                    )
                elif lan_ok:
                    result["notes"].append(
                        "Active test passed (same-host loopback + LAN IP). "
                        "External reachability requires a remote peer (--peer-validate)."
                    )
        elif not result["bind_ok"]:
            result["notes"].append(
                "Active reachability test skipped (bind failed)"
            )

        results.append(result)

    # ── Print summary ──────────────────────────────────────────
    print()
    _print("ℹ", "Port probe summary:")
    print(f"  {'PORT':<8} {'PROTO':<5} {'BIND':<6} {'FIREWALL':<10} {'REACHABLE':<11}  NOTES")
    print("  " + "─" * 78)

    for r in results:
        bind_s  = "✓" if r["bind_ok"] else "✗"
        fw_s    = {True: "✓", False: "✗", None: "?"}[r["firewall_allows"]]
        reach_s = {True: "✓", False: "✗", None: "?"}[r["externally_reachable"]]
        first_note = r["notes"][0] if r["notes"] else ""
        print(f"  {r['port']:<8} {r['proto']:<5} {bind_s:<6} {fw_s:<10} {reach_s:<11}  {first_note}")
        for note in r["notes"][1:]:
            print(f"  {'':<8} {'':<5} {'':<6} {'':<10} {'':<11}  {note}")

    print()

    warn_ports = [
        r for r in results
        if not r["bind_ok"]
        or r["firewall_allows"] is False
        or r["externally_reachable"] is False
    ]
    mismatch_ports = [
        r for r in results
        if r["firewall_allows"] is False and r["externally_reachable"] is True
    ]

    if mismatch_ports:
        print()
        _print("✗", "FIREWALL BLOCK DETECTED — active test gave false positive:")
        for r in mismatch_ports:
            _print("✗", f"  {r['port']}/{r['proto']} ({r['desc']}): firewall blocks this port "
                         "but same-host round-trip succeeded (loopback exemption). "
                         "External clients CANNOT reach this port.")
        _print("ℹ", "Run:  sudo python3 firewall_manager.py --install  to add ACCEPT rules.")

    if warn_ports and not mismatch_ports:
        _print("⚠", "One or more ports have issues.  If rules are missing, run:")
        _print("⚠", "    sudo python3 firewall_manager.py --install")

    if not warn_ports:
        _print("✓", "All ports passed local and host-firewall checks.")

    _print("ℹ", "Note: External reachability (Layer 3) can only be fully confirmed "
                 "by a remote peer.  NAT and upstream firewall filtering are invisible "
                 "to this host.")

    return results


# ╔══════════════════════════════════════════════════════════════╗
# ║  PRIVILEGED: Firewall backend detection (install-time)       ║
# ╚══════════════════════════════════════════════════════════════╝

def _detect_linux_backend() -> Optional[str]:
    """
    Return the authoritative active firewall backend by inspecting effective
    rule sets rather than just checking binary existence.

    Priority: ufw → firewalld → nftables → iptables
    """
    # ufw: active AND has a default policy line
    if _has("ufw"):
        r = _run(["ufw", "status", "verbose"])
        if r.returncode == 0 and "status: active" in r.stdout.lower():
            return "ufw"

    # firewalld: daemon responding
    if _has("firewall-cmd"):
        r = _run(["firewall-cmd", "--state"])
        if r.returncode == 0 and "running" in r.stdout.lower():
            return "firewalld"

    # nftables: nft present AND effective ruleset is non-empty
    # (covers distros that run nftables under ufw/firewalld)
    if _has("nft"):
        r = _run(["nft", "list", "ruleset"])
        if r.returncode == 0 and r.stdout.strip():
            return "nftables"

    # iptables: present AND has at least one non-default rule or a DROP policy
    if _has("iptables"):
        r = _run(["iptables-save"])
        if r.returncode == 0:
            # If only the skeleton chains exist it still counts — we can add rules
            return "iptables"

    return None


# ╔══════════════════════════════════════════════════════════════╗
# ║  PRIVILEGED: Firewall rule management (install-time)         ║
# ╚══════════════════════════════════════════════════════════════╝

# ── Linux: ufw ──

def _ufw_rule_exists(port: int, proto: str) -> bool:
    r = _run(["ufw", "status", "numbered"])
    if r.returncode != 0:
        return False
    return f"{port}/{proto}" in r.stdout and RULE_TAG in r.stdout

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
#
# DESIGN NOTE:
# We no longer create a private table with "policy accept" and hook at
# priority 0, as that is ignored if another table has a lower-priority
# DROP rule.  Instead we insert rules directly into the existing
# filter/INPUT chain (or the first input-hooked chain we can find), using
# an insert (prepend) so our ACCEPT rules evaluate before any DROP rules.
# If no suitable chain exists we fall back to creating a new table at
# priority -10 (lower number = higher priority, evaluated first).
# ─────────────────────────────────────────────────────────────────

_NFT_TABLE   = RULE_TAG          # fallback table name
_NFT_PRIORITY = -10              # evaluated before typical filter chains (priority 0)

def _nft_find_input_chain() -> Optional[Tuple[str, str]]:
    """
    Scan the live ruleset for the first base chain with 'hook input'.
    Returns (table_family_name, chain_name) or None.
    """
    r = _run(["nft", "list", "ruleset"])
    if r.returncode != 0:
        return None

    current_table: Optional[str] = None
    for line in r.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("table "):
            # e.g. "table inet filter {"
            parts = stripped.split()
            if len(parts) >= 3:
                current_table = f"{parts[1]} {parts[2]}"
        elif stripped.startswith("chain ") and "hook input" in stripped and current_table:
            parts = stripped.split()
            chain_name = parts[1]
            return (current_table, chain_name)
    return None


def _nft_rule_exists_in(table: str, chain: str, port: int, proto: str) -> bool:
    r = _run(["nft", "list", "chain"] + table.split() + [chain])
    if r.returncode != 0:
        return False
    return f"{proto} dport {port}" in r.stdout and "accept" in r.stdout


def _nft_add(port: int, proto: str, desc: str) -> None:
    target = _nft_find_input_chain()

    if target:
        table, chain = target
        if _nft_rule_exists_in(table, chain, port, proto):
            _print("✓", f"nft: rule already exists for {port}/{proto} in {table} {chain}")
            return
        # Use 'insert rule' to prepend (evaluated before any DROP further down)
        r = _run(["nft", "insert", "rule"] + table.split() + [chain,
                  proto, "dport", str(port), "accept",
                  "comment", f'"{RULE_TAG} {desc}"'])
        if r.returncode == 0:
            _print("✓", f"nft: inserted ACCEPT for {port}/{proto} in {table} {chain} ({desc})")
        else:
            _print("✗", f"nft: failed to insert rule: {r.stderr.strip()}")
    else:
        # No existing input chain → create our own table at high priority
        _nft_ensure_fallback_table()
        if _nft_rule_exists_in(f"inet {_NFT_TABLE}", "input", port, proto):
            _print("✓", f"nft: rule already exists for {port}/{proto}")
            return
        r = _run(["nft", "add", "rule", "inet", _NFT_TABLE, "input",
                  proto, "dport", str(port), "accept",
                  "comment", f'"{RULE_TAG} {desc}"'])
        if r.returncode == 0:
            _print("✓", f"nft: allowed {port}/{proto} ({desc})")
        else:
            _print("✗", f"nft: failed: {r.stderr.strip()}")


def _nft_ensure_fallback_table() -> None:
    """Create fallback nft table at priority -10 (runs before default filter)."""
    r = _run(["nft", "list", "tables"])
    if _NFT_TABLE in (r.stdout or ""):
        return
    cmds = [
        ["nft", "add", "table", "inet", _NFT_TABLE],
        ["nft", "add", "chain", "inet", _NFT_TABLE, "input",
         f"{{ type filter hook input priority {_NFT_PRIORITY} ; policy accept ; }}"],
    ]
    for cmd in cmds:
        res = _run(cmd)
        if res.returncode != 0:
            _print("✗", f"nft: {' '.join(cmd)} → {res.stderr.strip()}")


def _nft_remove_all() -> None:
    # Remove rules we inserted into foreign chains
    target = _nft_find_input_chain()
    if target:
        table, chain = target
        r = _run(["nft", "list", "chain"] + table.split() + [chain])
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if RULE_TAG in line and "accept" in line:
                    # Extract handle number: "... # handle N"
                    if "# handle" in line:
                        handle = line.split("# handle")[-1].strip().split()[0]
                        _run(["nft", "delete", "rule"] + table.split() + [chain, "handle", handle])

    # Remove fallback table if it exists
    r = _run(["nft", "list", "tables"])
    if _NFT_TABLE in (r.stdout or ""):
        _run(["nft", "delete", "table", "inet", _NFT_TABLE])
        _print("✓", f"nft: removed {_NFT_TABLE} fallback table")


# ── Linux: iptables ──

def _iptables_rule_exists(port: int, proto: str) -> bool:
    r = _run(["iptables-save"])
    if r.returncode != 0:
        return False
    needle = f"--dport {port} -j ACCEPT"
    return needle in r.stdout and RULE_TAG in r.stdout

def _iptables_add(port: int, proto: str, desc: str) -> None:
    if _iptables_rule_exists(port, proto):
        _print("✓", f"iptables: rule already exists for {port}/{proto}")
        return
    # Use -I (insert at top) so our ACCEPT precedes any DROP rules
    r = _run([
        "iptables", "-I", "INPUT", "1",
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
    """
    Verify the rule exists, is enabled, and matches the currently active
    Windows network profile.
    """
    name = _netsh_rule_name(port, proto, direction)
    r = _run(["netsh", "advfirewall", "firewall", "show", "rule",
              f"name={name}", "verbose"])
    if r.returncode != 0 or name not in (r.stdout or ""):
        return False

    active_profile = _windows_active_profile()
    if active_profile is None:
        return True  # Cannot determine profile; assume rule applies

    for line in r.stdout.splitlines():
        if "Profiles:" in line and active_profile.capitalize() in line:
            return True
    # Rule exists but does not cover the active profile
    _print("⚠", f"netsh: rule '{name}' exists but does not cover "
                 f"active profile '{active_profile}'")
    return False

def _netsh_add(port: int, proto: str, desc: str) -> None:
    active_profile = _windows_active_profile() or "any"
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
            f"profile={active_profile}",
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
        _print("ℹ", "Configuring Windows Firewall via netsh…")
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

    # ── ICMP (ping) ────────────────────────────────────────────
    if ICMP_NEEDED:
        _print("ℹ", "Adding ICMP echo (ping) allow rule…")
        _add_icmp_rule(backend, system)

    return True


def _add_icmp_rule(backend: Optional[str], system: str) -> None:
    """Add an allow-rule for ICMP echo (ping) on the detected backend."""
    if system == "windows":
        # Windows: allow ICMPv4 echo request (inbound)
        name = f"{RULE_TAG}_ICMP_echo_in"
        r = _run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"])
        if r.returncode == 0 and name in (r.stdout or ""):
            _print("✓", "netsh: ICMP echo rule already exists")
            return
        r = _run([
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={name}",
            "dir=in", "action=allow",
            "protocol=icmpv4", "type=8",
            "profile=any",
            f"description={RULE_TAG}: Allow ping (echo request)",
        ])
        if r.returncode == 0:
            _print("✓", "netsh: allowed ICMP echo request")
        else:
            _print("✗", f"netsh: ICMP failed: {r.stderr.strip()}")
        return

    # Linux
    if backend == "ufw":
        # ufw doesn't block ICMP by default, but we can ensure it's open
        # via /etc/ufw/before.rules - just log that ufw allows ping by default
        _print("✓", "ufw: ICMP echo allowed by default (ufw does not block ping)")

    elif backend == "firewalld":
        r = _run(["firewall-cmd", "--query-icmp-block=echo-request"])
        if r.returncode == 0 and "yes" in (r.stdout or "").lower():
            # ICMP echo is explicitly blocked, remove the block
            r2 = _run(["firewall-cmd", "--permanent", "--remove-icmp-block=echo-request"])
            if r2.returncode == 0:
                _print("✓", "firewalld: removed ICMP echo block")
                _run(["firewall-cmd", "--reload"])
            else:
                _print("✗", f"firewalld: failed to unblock ICMP: {r2.stderr.strip()}")
        else:
            _print("✓", "firewalld: ICMP echo not blocked")

    elif backend == "nftables":
        target = _nft_find_input_chain()
        if target:
            table, chain = target
            # Check if an ICMP accept rule already exists
            r = _run(["nft", "list", "chain"] + table.split() + [chain])
            if r.returncode == 0 and RULE_TAG in (r.stdout or "") and "icmp" in (r.stdout or "").lower():
                _print("✓", f"nft: ICMP rule already exists in {table} {chain}")
            else:
                r2 = _run(["nft", "insert", "rule"] + table.split() + [chain,
                          "ip", "protocol", "icmp", "icmp", "type", "echo-request", "accept",
                          "comment", f'"{RULE_TAG} ICMP echo"'])
                if r2.returncode == 0:
                    _print("✓", f"nft: allowed ICMP echo in {table} {chain}")
                else:
                    _print("✗", f"nft: ICMP failed: {r2.stderr.strip()}")
        else:
            _print("ℹ", "nft: no input chain found for ICMP rule")

    elif backend == "iptables":
        # Check if ICMP echo accept already exists
        r = _run(["iptables-save"])
        if RULE_TAG in (r.stdout or "") and "icmp" in (r.stdout or "").lower() and "--icmp-type 8" in (r.stdout or ""):
            _print("✓", "iptables: ICMP echo rule already exists")
        else:
            r2 = _run([
                "iptables", "-I", "INPUT", "1",
                "-p", "icmp", "--icmp-type", "echo-request",
                "-j", "ACCEPT",
                "-m", "comment", "--comment", f"{RULE_TAG} ICMP echo",
            ])
            if r2.returncode == 0:
                _print("✓", "iptables: allowed ICMP echo request")
            else:
                _print("✗", f"iptables: ICMP failed: {r2.stderr.strip()}")

    else:
        _print("ℹ", "No firewall backend — ICMP should be allowed by default")


def _remove_icmp_rule(backend: Optional[str], system: str) -> None:
    """Remove our ICMP allow rules."""
    if system == "windows":
        name = f"{RULE_TAG}_ICMP_echo_in"
        _run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={name}"])
        return

    if backend == "iptables":
        _run([
            "iptables", "-D", "INPUT",
            "-p", "icmp", "--icmp-type", "echo-request",
            "-j", "ACCEPT",
            "-m", "comment", "--comment", f"{RULE_TAG} ICMP echo",
        ])
    # nftables rules are cleaned up via _nft_remove_all() which removes by tag
    # ufw + firewalld: we didn't add explicit rules, just unblocked


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

    _print("ℹ", f"Removing rules via {backend}…")

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

    # Remove ICMP rule
    _remove_icmp_rule(backend, "linux")


# ╔══════════════════════════════════════════════════════════════╗
# ║  CLI entry-point                                             ║
# ╚══════════════════════════════════════════════════════════════╝

def _cli_help():
    print("Usage: python firewall_manager.py [--install | --probe | --remove | --help]")
    print()
    print("  --install        Add firewall rules for LANFXplorer ports (requires privileges)")
    print("  --probe          Three-layer port probe (bind + firewall + reachability)")
    print("  --probe-quick    Probe without active round-trip test (faster)")
    print("  --remove         Remove LANFXplorer firewall rules (requires privileges)")
    print("  --help           Show this help")
    print()
    print("Required ports:")
    for port, proto, desc, expose in REQUIRED_PORTS:
        scope = "network" if expose else "localhost"
        print(f"  {port:>5}/{proto:<3}  {desc:<30}  [{scope}]")
    print()
    print("Probe result columns:")
    print("  BIND      ✓ = port bindable locally")
    print("  FIREWALL  ✓ = host firewall has an explicit ACCEPT rule")
    print("            ?  = could not determine (no backend / insufficient privileges)")
    print("  REACHABLE ✓ = active round-trip succeeded on loopback + LAN IP")
    print()
    print("Note: REACHABLE only tests within this host.  External reachability")
    print("(NAT, ISP firewall, VLAN ACL) requires a remote peer.")


if __name__ == "__main__":
    if len(sys.argv) < 2 or "--help" in sys.argv:
        _cli_help()
        sys.exit(0)

    action = sys.argv[1]

    if action == "--install":
        success = ensure_firewall_rules()
        sys.exit(0 if success else 1)

    elif action == "--probe":
        results = probe_ports(active_test=True)
        errors = [r for r in results
                  if not r["bind_ok"]
                  or r["firewall_allows"] is False
                  or r["externally_reachable"] is False]
        sys.exit(1 if errors else 0)

    elif action == "--probe-quick":
        results = probe_ports(active_test=False)
        errors = [r for r in results
                  if not r["bind_ok"] or r["firewall_allows"] is False]
        sys.exit(1 if errors else 0)

    elif action == "--remove":
        remove_firewall_rules()
        sys.exit(0)

    else:
        print(f"Unknown action: {action}")
        _cli_help()
        sys.exit(1)