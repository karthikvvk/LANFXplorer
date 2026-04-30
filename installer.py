import os
import sys
import platform
import subprocess
import shutil
import getpass
import argparse
import time
from pathlib import Path

# Application directory
APP_DIR = Path(__file__).parent.resolve()
SYSTEM = platform.system().lower()

# Ports used by the application
PORTS = {
    4433: ("UDP", "QUIC File Transfer"),
    4434: ("UDP", "CA Discovery"),
    4435: ("TCP", "CA Signing Service"),
    4436: ("UDP", "Peer Discovery"),
    4437: ("TCP", "Handshake Service"),
    5000: ("TCP", "API Bridge (Flask)"),
}


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def print_status(status: str, message: str, indent: int = 0):
    """Print a status message."""
    prefix = "  " * indent
    symbols = {"ok": "✓", "fail": "✗", "info": "ℹ", "warn": "⚠", "run": "→"}
    symbol = symbols.get(status, "•")
    print(f"{prefix}[{symbol}] {message}")


def run_command(cmd: list, capture: bool = True, check: bool = False, timeout: int = 120) -> tuple:
    """Run a command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=timeout,
            check=check
        )
        return True, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout or "", e.stderr or str(e)
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except FileNotFoundError:
        return False, "", f"Command not found: {cmd[0]}"
    except Exception as e:
        return False, "", str(e)


def elevate_if_needed():
    """Elevate to admin/root if not already elevated."""
    if SYSTEM.startswith("win"):
        import ctypes
        if not ctypes.windll.shell32.IsUserAnAdmin():
            try:
                import elevate
                elevate.elevate()
            except ImportError:
                print_status("warn", "elevate module not available. Run as Administrator manually.")
                return False
    else:
        if os.geteuid() != 0:
            try:
                import elevate
                elevate.elevate()
            except ImportError:
                print_status("warn", "elevate module not available. Run with sudo manually.")
                return False
    return True


def drop_privileges():
    """
    Drop back to normal user privileges after elevated operations.
    On Linux, this resets effective UID/GID to real UID/GID.
    On Windows, this is a no-op (Windows handles this differently).
    """
    print("droping prev")
    if SYSTEM.startswith("linux"):
        try:
            # Get the original user's UID/GID
            sudo_uid = os.environ.get('SUDO_UID')
            sudo_gid = os.environ.get('SUDO_GID')
            
            if sudo_uid and sudo_gid:
                # We were elevated via sudo, drop back
                os.setegid(int(sudo_gid))
                os.seteuid(int(sudo_uid))
                print_status("ok", "Dropped to normal user privileges")
            elif os.geteuid() == 0:
                # Running as root but not via sudo - just continue
                print_status("info", "Running as root, continuing...")
            # else: already running as normal user, nothing to do
        except PermissionError:
            # Can't drop privileges - likely not elevated
            pass
        except Exception as e:
            print_status("warn", f"Could not drop privileges: {e}")
    # Windows: no-op, subprocess calls with "runas" don't persist elevation
    return True


# =============================================================================
# Dependency Checker
# =============================================================================

class DependencyChecker:
    """Check and install system dependencies."""

    @staticmethod
    def check_python() -> bool:
        """Check if Python 3.8+ is available."""
        version = sys.version_info
        if version.major >= 3 and version.minor >= 8:
            print_status("ok", f"Python {version.major}.{version.minor}.{version.micro} detected")
            return True
        print_status("fail", f"Python 3.8+ required, found {version.major}.{version.minor}")
        return False


    @staticmethod
    def check_flutter() -> bool:
        """Check if Flutter is installed."""
        success, stdout, _ = run_command(["flutter", "--version"])
        if success:
            # Extract first line which contains version
            version_line = stdout.split('\n')[0] if stdout else "unknown"
            print_status("ok", f"Flutter detected: {version_line}")
            return True
        print_status("fail", "Flutter not found")
        return False

    @staticmethod
    def check_pip() -> bool:
        """Check if pip is available."""
        success, stdout, _ = run_command([sys.executable, "-m", "pip", "--version"])
        if success:
            print_status("ok", f"pip detected: {stdout.strip()[:50]}...")
            return True
        print_status("fail", "pip not found")
        return False
    @staticmethod
    def check_iw() -> bool:
        """Check if iw is installed (used for WiFi link speed detection)."""
        success, stdout, _ = run_command(["iw", "--version"])
        if success and stdout:
            print_status("ok", f"iw detected: {stdout.strip().splitlines()[0]}")
            return True
        print_status("fail", "iw not found (needed for WiFi speed detection)")
        return False

    @staticmethod
    def check_iwconfig() -> bool:
        """Check if iwconfig is installed (wireless-tools, used for WiFi bit rate)."""
        success, stdout, _ = run_command(["iwconfig", "--version"])
        # iwconfig prints to stderr on --version, so just check it exists
        if success or shutil.which("iwconfig"):
            print_status("ok", "iwconfig (wireless-tools) detected")
            return True
        print_status("fail", "iwconfig not found (needed for WiFi speed detection)")
        return False

    @staticmethod
    def install_wireless_tools_linux() -> bool:
        """Install iw and wireless-tools on Linux."""
        print_status("run", "Attempting to install iw and wireless-tools...")

        pkg_managers = [
            (["apt-get", "--version"], ["sudo", "apt-get", "install", "-y", "iw", "wireless-tools"]),
            (["dnf", "--version"],     ["sudo", "dnf",     "install", "-y", "iw", "wireless-tools"]),
            (["yum", "--version"],     ["sudo", "yum",     "install", "-y", "iw", "wireless-tools"]),
            (["pacman", "--version"],  ["sudo", "pacman",  "-S", "--noconfirm", "iw", "wireless_tools"]),
            (["zypper", "--version"],  ["sudo", "zypper",  "install", "-y", "iw", "wireless-tools"]),
        ]

        for check_cmd, install_cmd in pkg_managers:
            success, _, _ = run_command(check_cmd)
            if success:
                success, _, stderr = run_command(install_cmd, timeout=300)
                if success:
                    print_status("ok", "iw and wireless-tools installed successfully")
                    return True
                else:
                    print_status("fail", f"Failed to install wireless tools: {stderr}")
                    return False

        print_status("fail", "No supported package manager found")
        return False






    def check_all(self) -> dict:
        """Check all dependencies and return status."""
        print_header("Checking System Dependencies")
        # NOTE: No standalone OpenSSL check — the cryptography pip package
        # bundles its own OpenSSL via cffi. No system binary is required.
        results = {
            "python":  self.check_python(),
            "pip":     self.check_pip(),
            "flutter": self.check_flutter(),
        }
        # Wireless tools are Linux-only
        if SYSTEM.startswith("linux"):
            results["iw"]       = self.check_iw()
            results["iwconfig"] = self.check_iwconfig()
        return results


# =============================================================================
# Firewall Manager
# =============================================================================

class FirewallManager:
    """Configure firewall rules for the application with robust bidirectional support."""

    def __init__(self):
        self.needs_elevation = True
        self.app_name = "LANFXplorer"

    def _get_firewall_tool_linux(self) -> str:
        """Detect available firewall tool on Linux."""
        tools = ["ufw", "firewall-cmd", "iptables"]
        for tool in tools:
            if shutil.which(tool):
                return tool
        return ""

    def _cleanup_existing_rules_ufw(self) -> bool:
        """Remove any conflicting or stale UFW rules for our ports."""
        # UFW doesn't have a good way to delete by port, so we skip cleanup
        # Rules are idempotent - adding same rule again is safe
        return True

    def allow_port_linux(self, port: int, protocol: str, direction: str = "in") -> bool:
        """
        Allow a port on Linux firewall.
        
        Args:
            port: Port number
            protocol: 'tcp' or 'udp'
            direction: 'in', 'out', or 'both'
        """
        tool = self._get_firewall_tool_linux()
        proto = protocol.lower()

        if tool == "ufw":
            # UFW: allow in/out
            if direction in ("in", "both"):
                run_command(["sudo", "ufw", "allow", "in", f"{port}/{proto}"], 
                           capture=True)
            if direction in ("out", "both"):
                run_command(["sudo", "ufw", "allow", "out", f"{port}/{proto}"],
                           capture=True)
            return True
            
        elif tool == "firewall-cmd":
            # Firewalld: add-port handles both directions by default
            success, _, _ = run_command([
                "sudo", "firewall-cmd", "--permanent",
                f"--add-port={port}/{proto}"
            ])
            return success
            
        elif tool == "iptables":
            success = True
            if direction in ("in", "both"):
                s, _, _ = run_command([
                    "sudo", "iptables", "-A", "INPUT",
                    "-p", proto, "--dport", str(port),
                    "-j", "ACCEPT"
                ])
                success = success and s
            if direction in ("out", "both"):
                s, _, _ = run_command([
                    "sudo", "iptables", "-A", "OUTPUT",
                    "-p", proto, "--dport", str(port),
                    "-j", "ACCEPT"
                ])
                success = success and s
            return success
        else:
            print_status("warn", "No firewall tool found. Manual configuration may be needed.", 1)
            return True

    def allow_icmp_linux(self) -> bool:
        """Allow ICMP (ping) for network discovery."""
        tool = self._get_firewall_tool_linux()
        
        if tool == "ufw":
            # UFW allows ICMP by default, but we ensure it's enabled
            # Check /etc/ufw/before.rules for ICMP settings
            print_status("info", "ICMP/ping allowed (UFW default)", 1)
            return True
            
        elif tool == "firewall-cmd":
            run_command([
                "sudo", "firewall-cmd", "--permanent",
                "--add-icmp-block-inversion"  # Allow ICMP
            ])
            return True
            
        elif tool == "iptables":
            run_command([
                "sudo", "iptables", "-A", "INPUT",
                "-p", "icmp", "--icmp-type", "echo-request",
                "-j", "ACCEPT"
            ])
            run_command([
                "sudo", "iptables", "-A", "OUTPUT",
                "-p", "icmp", "--icmp-type", "echo-reply",
                "-j", "ACCEPT"
            ])
            return True
        return True

    def allow_broadcast_linux(self) -> bool:
        """Allow UDP broadcast for peer discovery."""
        tool = self._get_firewall_tool_linux()
        
        if tool == "ufw":
            # UFW: Allow broadcast on discovery port
            # Broadcast is typically allowed by default, but let's be explicit
            run_command(["sudo", "ufw", "allow", "in", "from", "any", "to", "255.255.255.255", 
                        "port", "4436", "proto", "udp"], capture=True)
            return True
            
        elif tool == "iptables":
            # Allow broadcast traffic
            run_command([
                "sudo", "iptables", "-A", "INPUT",
                "-d", "255.255.255.255",
                "-p", "udp", "--dport", "4436",
                "-j", "ACCEPT"
            ])
            run_command([
                "sudo", "iptables", "-A", "INPUT",
                "-m", "pkttype", "--pkt-type", "broadcast",
                "-p", "udp", "--dport", "4436",
                "-j", "ACCEPT"
            ])
            return True
        return True

    def allow_port_windows(self, port: int, protocol: str) -> bool:
        """Allow a port on Windows firewall with both inbound and outbound rules."""
        proto = protocol.upper()
        
        # Inbound rule
        rule_name_in = f"{self.app_name}_{proto}_{port}_IN"
        run_command([
            "netsh", "advfirewall", "firewall", "delete", "rule",
            f"name={rule_name_in}"
        ])
        run_command([
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={rule_name_in}",
            "dir=in",
            "action=allow",
            f"protocol={proto}",
            f"localport={port}",
            "enable=yes"
        ])
        
        # Outbound rule
        rule_name_out = f"{self.app_name}_{proto}_{port}_OUT"
        run_command([
            "netsh", "advfirewall", "firewall", "delete", "rule",
            f"name={rule_name_out}"
        ])
        run_command([
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={rule_name_out}",
            "dir=out",
            "action=allow",
            f"protocol={proto}",
            f"localport={port}",
            "enable=yes"
        ])
        
        return True

    def allow_icmp_windows(self) -> bool:
        """Allow ICMP (ping) on Windows."""
        rule_name = f"{self.app_name}_ICMP"
        run_command([
            "netsh", "advfirewall", "firewall", "delete", "rule",
            f"name={rule_name}"
        ])
        run_command([
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={rule_name}",
            "protocol=icmpv4:8,any",
            "dir=in",
            "action=allow",
            "enable=yes"
        ])
        return True

    def allow_port(self, port: int, protocol: str) -> bool:
        """Allow a port in the firewall (both directions)."""
        if SYSTEM.startswith("linux"):
            return self.allow_port_linux(port, protocol, direction="both")
        elif SYSTEM.startswith("win"):
            return self.allow_port_windows(port, protocol)
        return False

    def configure_all_ports(self) -> bool:
        """Configure all required ports with robust rules."""
        print_header("Configuring Firewall Rules")

        if self.needs_elevation:
            print_status("info", "Firewall configuration may require elevated privileges")

        all_success = True
        
        # Configure application ports (bidirectional)
        for port, (protocol, description) in PORTS.items():
            success = self.allow_port(port, protocol)
            if success:
                print_status("ok", f"Port {port}/{protocol} (in/out) - {description}", 1)
            else:
                print_status("fail", f"Port {port}/{protocol} - {description}", 1)
                all_success = False

        # Configure ICMP for network discovery
        if SYSTEM.startswith("linux"):
            self.allow_icmp_linux()
        elif SYSTEM.startswith("win"):
            self.allow_icmp_windows()
        print_status("ok", "ICMP/ping enabled for discovery", 1)
        
        # Configure broadcast for peer discovery (Linux only)
        if SYSTEM.startswith("linux"):
            self.allow_broadcast_linux()
            print_status("ok", "UDP broadcast enabled for peer discovery", 1)

        # Enable/reload firewall
        if SYSTEM.startswith("linux"):
            tool = self._get_firewall_tool_linux()
            if tool == "ufw":
                run_command(["sudo", "ufw", "--force", "enable"])
                print_status("ok", "UFW firewall enabled")
            elif tool == "firewall-cmd":
                run_command(["sudo", "firewall-cmd", "--reload"])
                print_status("ok", "Firewalld reloaded")
        
        # Drop back to normal user privileges after firewall config
        drop_privileges()

        return all_success


# =============================================================================
# Requirements Installer
# =============================================================================

class RequirementsInstaller:
    """Install Python requirements."""

    def __init__(self):
        self.requirements_file = APP_DIR / "requirements.txt"
        # self.old_requirements_file = APP_DIR / "requirement.txtt"

    def create_requirements_file(self):
        """Create a proper requirements.txt file."""
        # NOTE: pyOpenSSL, service-identity, aioquic, ownca removed.
        # QUIC transport now uses MsQuic CLI binaries.
        # cryptography lib bundles its own OpenSSL — no system openssl needed.
        requirements = [
            "paramiko",
            "requests",
            "flask",
            "python-dotenv",
            "elevate",
            "scapy",
            "cryptography>=42.0,<46.0",
            "bcrypt",
            "keyring",
            "SecretStorage",
            "keyrings.alt",
        ]

        with open(self.requirements_file, "w") as f:
            f.write("\n".join(requirements) + "\n")
        
        print_status("ok", f"Created {self.requirements_file}")

    def upgrade_pip(self) -> bool:
        """Upgrade pip to latest version."""
        print_status("run", "Upgrading pip...")
        success, _, stderr = run_command(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
            timeout=120
        )
        if success:
            print_status("ok", "pip upgraded")
        else:
            print_status("warn", f"pip upgrade failed: {stderr[:50]}")
        return success

    def install_requirements(self) -> bool:
        """Install Python requirements."""
        print_header("Installing Python Requirements")

        # Create requirements.txt if it doesn't exist
        if not self.requirements_file.exists():
            self.create_requirements_file()

        # Upgrade pip first
        self.upgrade_pip()

        # Install requirements
        print_status("run", "Installing packages from requirements.txt...")
        success, stdout, stderr = run_command(
            [sys.executable, "-m", "pip", "install", "-r", str(self.requirements_file)],
            timeout=600
        )

        if success:
            print_status("ok", "All requirements installed successfully")
            return True
        else:
            print_status("fail", f"Requirements installation failed")
            print(f"      Error: {stderr[:200]}")
            return False


# =============================================================================
# Directory Manager
# =============================================================================

class DirectoryManager:
    """Manage application directories."""

    def __init__(self):
        self.home = Path.home()
        self.lanfxplorer_dir = self.home / "Lanfxplorer"
        self.pki_dir = APP_DIR / "pki"
        self.pki_export_dir = APP_DIR / "pkica_export"

    def ensure_lanfxplorer_dir(self) -> Path:
        """Ensure the Lanfxplorer directory exists."""
        self.lanfxplorer_dir.mkdir(parents=True, exist_ok=True)
        print_status("ok", f"Lanfxplorer directory: {self.lanfxplorer_dir}")
        return self.lanfxplorer_dir

    def ensure_pki_dirs(self) -> bool:
        """Ensure PKI directories exist."""
        self.pki_dir.mkdir(parents=True, exist_ok=True)
        self.pki_export_dir.mkdir(parents=True, exist_ok=True)
        print_status("ok", f"PKI directories created")
        return True

    def setup_all(self) -> bool:
        """Set up all required directories."""
        print_header("Setting Up Directories")
        self.ensure_lanfxplorer_dir()
        self.ensure_pki_dirs()
        return True


# =============================================================================
# Desktop Entry Manager
# =============================================================================

class DesktopEntryManager:
    """Create desktop entries for the application."""

    def __init__(self):
        self.app_name = "LANFXplorer"
        self.app_dir = APP_DIR
        self.start_script = APP_DIR / "start.py"


    def create_linux_desktop_entry(self) -> bool:
        """Create a .desktop file on Linux."""
        applications_dir = Path.home() / ".local" / "share" / "applications"
        applications_dir.mkdir(parents=True, exist_ok=True)

        desktop_file = applications_dir / "lanfxplorer.desktop"

        # Find Python executable
        python_exec = sys.executable

        # Look for an icon (create a simple one if not exists)
        icon_path = self.app_dir / "assets" / "icon.png"
        if not icon_path.exists():
            icon_path = ""  # Use default icon

        desktop_content = f"""[Desktop Entry]
Name={self.app_name}
Comment=LAN File Explorer with QUIC Protocol
Exec={python_exec} {self.start_script}
Icon={icon_path if icon_path else 'network-workgroup'}
Terminal=false
Type=Application
Categories=Network;FileTransfer;Utility;
StartupNotify=true
"""

        with open(desktop_file, "w") as f:
            f.write(desktop_content)

        # Make it executable
        os.chmod(desktop_file, 0o755)

        print_status("ok", f"Created desktop entry: {desktop_file}")
        
        # Also create on Desktop if exists
        desktop_path = Path.home() / "Desktop"
        if desktop_path.exists():
            desktop_shortcut = desktop_path / "LANFXplorer.desktop"
            with open(desktop_shortcut, "w") as f:
                f.write(desktop_content)
            os.chmod(desktop_shortcut, 0o755)
            print_status("ok", f"Created desktop shortcut: {desktop_shortcut}")

        return True

    def create_windows_shortcut(self) -> bool:
        """Create a shortcut on Windows."""
        try:
            import winshell
            from win32com.client import Dispatch
        except ImportError:
            # Fallback to PowerShell
            return self._create_windows_shortcut_powershell()

        desktop = Path(winshell.desktop())
        shortcut_path = desktop / f"{self.app_name}.lnk"

        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.Targetpath = sys.executable
        shortcut.Arguments = str(self.start_script)
        shortcut.WorkingDirectory = str(self.app_dir)
        shortcut.Description = "LANFXplorer - LAN File Transfer"
        shortcut.save()

        print_status("ok", f"Created Windows shortcut: {shortcut_path}")
        return True

    def _create_windows_shortcut_powershell(self) -> bool:
        """Create Windows shortcut using PowerShell."""
        desktop = Path.home() / "Desktop"
        shortcut_path = desktop / f"{self.app_name}.lnk"

        ps_script = f'''
$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
$Shortcut.TargetPath = "{sys.executable}"
$Shortcut.Arguments = '"{self.start_script}"'
$Shortcut.WorkingDirectory = "{self.app_dir}"
$Shortcut.Description = "LANFXplorer - LAN File Transfer"
$Shortcut.Save()
'''
        success, _, stderr = run_command([
            "powershell", "-NoProfile", "-Command", ps_script
        ])

        if success:
            print_status("ok", f"Created Windows shortcut: {shortcut_path}")
        else:
            print_status("fail", f"Failed to create Windows shortcut: {stderr}")

        return success

    def create_desktop_entry(self) -> bool:
        """Create desktop entry based on OS."""
        print_header("Creating Desktop Entry")

        # First create the start script
        # self.create_start_script()

        if SYSTEM.startswith("linux"):
            return self.create_linux_desktop_entry()
        elif SYSTEM.startswith("win"):
            return self.create_windows_shortcut()
        else:
            print_status("warn", f"Desktop entry not supported on {SYSTEM}")
            return False


# =============================================================================
# Application Launcher
# =============================================================================

class AppLauncher:
    """Launch the application components."""

    def __init__(self):
        self.app_dir = APP_DIR
        self.processes = []

    def start_process(self, script: str, name: str, wait: bool = False) -> subprocess.Popen:
        """Start a Python script as a subprocess."""
        script_path = self.app_dir / script
        if not script_path.exists():
            print_status("fail", f"{name}: Script not found - {script_path}")
            return None

        print_status("run", f"Starting {name}...")
        
        try:
            proc = subprocess.Popen(
                [sys.executable, str(script_path)],
                cwd=str(self.app_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            if wait:
                # Wait for process to complete
                proc.wait()
                if proc.returncode == 0:
                    print_status("ok", f"{name} completed")
                else:
                    print_status("fail", f"{name} failed with code {proc.returncode}")
            else:
                # Give it a moment to start
                time.sleep(1)
                if proc.poll() is None:
                    print_status("ok", f"{name} started (PID: {proc.pid})")
                    self.processes.append((name, proc))
                else:
                    _, stderr = proc.communicate()
                    print_status("fail", f"{name} failed to start: {stderr.decode()[:100]}")
                    return None
            
            return proc
        except Exception as e:
            print_status("fail", f"{name} error: {str(e)}")
            return None

    def start_flutter(self) -> subprocess.Popen:
        """Start the Flutter application."""
        print_status("run", "Starting Flutter application...")
        
        try:
            proc = subprocess.Popen(
                ["flutter", "run", "-d", "linux"],
                cwd=str(self.app_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            time.sleep(2)
            if proc.poll() is None:
                print_status("ok", f"Flutter started (PID: {proc.pid})")
                self.processes.append(("Flutter", proc))
                return proc
            else:
                _, stderr = proc.communicate()
                print_status("fail", f"Flutter failed to start: {stderr.decode()[:100]}")
                return None
        except FileNotFoundError:
            print_status("fail", "Flutter not found in PATH")
            return None
        except Exception as e:
            print_status("fail", f"Flutter error: {str(e)}")
            return None

    def stop_all(self):
        """Stop all running processes."""
        print_status("info", "Stopping all services...")
        for name, proc in self.processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                    print_status("ok", f"{name} stopped")
                except subprocess.TimeoutExpired:
                    proc.kill()
                    print_status("warn", f"{name} killed")

    def run(self):
        """Run the complete application startup sequence."""
        print_header("Starting LANFXplorer")

        try:
            # 1. Run startsetup.py (wait for it to complete)
            self.start_process("startsetup.py", "PKI Setup", wait=True)
            
            # 2. Start recive.py (background)
            receiver = self.start_process("recive.py", "QUIC Receiver")
            if not receiver:
                print_status("fail", "Cannot start without receiver!")
                return
            
            # Wait a bit for receiver to initialize
            time.sleep(2)
            
            # 3. Start api_bridge.py (background)
            api = self.start_process("api_bridge.py", "API Bridge")
            if not api:
                print_status("warn", "API Bridge failed to start, continuing...")
            
            # Wait for API to be ready
            time.sleep(2)
            
            # 4. Start Flutter
            flutter = self.start_flutter()
            
            print_header("LANFXplorer Running")
            print_status("info", "Services running:")
            for name, proc in self.processes:
                print(f"        • {name} (PID: {proc.pid})")
            print("\n   Press Ctrl+C to stop all services\n")

            # Wait for Flutter to exit or Ctrl+C
            if flutter:
                flutter.wait()
            else:
                # If no Flutter, keep running until interrupted
                while True:
                    time.sleep(1)
                    # Check if any critical process died
                    if receiver and receiver.poll() is not None:
                        print_status("warn", "Receiver process died!")
                        break

        except KeyboardInterrupt:
            print("\n")
            print_status("info", "Shutdown requested...")
        finally:
            self.stop_all()


# =============================================================================
# Main Installer
# =============================================================================

class Installer:
    """Main installer class that orchestrates installation."""

    def __init__(self):
        self.dep_checker = DependencyChecker()
        self.firewall_mgr = FirewallManager()
        self.req_installer = RequirementsInstaller()
        self.dir_manager = DirectoryManager()
        self.desktop_mgr = DesktopEntryManager()
        self.launcher = AppLauncher()

    def check_dependencies(self) -> bool:
        """Check all dependencies."""
        results = self.dep_checker.check_all()

        # iw / wireless-tools (Linux only, non-critical but needed for WiFi speed)
        if SYSTEM.startswith("linux"):
            if not results.get("iw") or not results.get("iwconfig"):
                print_status("info", "Attempting to install iw and wireless-tools...")
                if not self.dep_checker.install_wireless_tools_linux():
                    print_status("warn", "Wireless tools installation failed. WiFi speed detection may not work.")

        return results["python"] and results["pip"]

    def configure_firewall(self) -> bool:
        """Configure firewall rules."""
        return self.firewall_mgr.configure_all_ports()

    def install_requirements(self) -> bool:
        """Install Python requirements."""
        return self.req_installer.install_requirements()

    def setup_directories(self) -> bool:
        """Set up required directories."""
        return self.dir_manager.setup_all()

    def create_desktop_entry(self) -> bool:
        """Create desktop entry."""
        return self.desktop_mgr.create_desktop_entry()

    def full_install(self) -> bool:
        """Perform full installation."""
        print_header("LANFXplorer Installer")
        print(f"   Platform: {platform.system()} {platform.release()}")
        print(f"   Python: {sys.version.split()[0]}")
        print(f"   App Directory: {APP_DIR}")

        steps = [
            ("Checking dependencies", self.check_dependencies),
            ("Installing requirements", self.install_requirements),
            ("Setting up directories", self.setup_directories),
            ("Configuring firewall", self.configure_firewall),
            ("Creating desktop entry", self.create_desktop_entry),
        ]

        all_success = True
        for step_name, step_func in steps:
            try:
                if not step_func():
                    print_status("warn", f"Step '{step_name}' had issues")
                    all_success = False
            except Exception as e:
                print_status("fail", f"Step '{step_name}' failed: {str(e)}")
                all_success = False

        if all_success:
            print_header("Installation Complete!")
            print_status("ok", "LANFXplorer is ready to use")
            print_status("info", "Run 'python installer.py --run' to start the application")
            print_status("info", "Or use the desktop shortcut")
        else:
            print_header("Installation Completed with Warnings")
            print_status("warn", "Some steps had issues but installation may still work")

        return all_success

    def run_app(self):
        """Run the application."""
        self.launcher.run()


def main():
    """Run full installation when called directly."""
    installer = Installer()
    installer.full_install()
    

if __name__ == "__main__":
    main()
