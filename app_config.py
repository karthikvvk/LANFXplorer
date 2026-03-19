"""
LANFXplorer App Configuration

Centralized configuration management with singleton pattern for thread-safe access.
This class handles all environment variables and provides a unified interface
for configuration across the application.

Design Pattern:
- Static truths (persisted): stored in .env file
- Dynamic/security-sensitive: accessed via class methods for thread-safety

Usage:
    from app_config import get_config
    
    config = get_config()
    port = config.QUIC_PORT  # Access constant
    host = config.host       # Access dynamic value
    
    # Reload from .env
    config.reload()
    
    # Get all as dictionary
    all_config = config.get_all()
"""

import os
import getpass
import platform
import threading
from pathlib import Path
from typing import Optional, Dict, Any

# Resolved once at import time — safe to use before _app_dir is set on the instance
_APP_DIR = Path(__file__).parent.resolve()


class AppConfig:
    """
    Singleton configuration manager for thread-safe access.
    
    Centralizes all port numbers, constants, and environment variables.
    Use get_config() to get the singleton instance.
    """
    
    # ==================== CENTRALIZED PORT CONSTANTS ====================
    # These are the canonical port definitions for the entire application
    QUIC_PORT = 4433          # QUIC File Transfer
    CA_DISCOVERY_PORT = 4434  # CA Discovery (UDP)
    CA_SIGNING_PORT = 4435    # CA Signing Service (TCP)
    PEER_DISCOVERY_PORT = 4436  # Peer Discovery (UDP)
    HANDSHAKE_PORT = 4437     # Handshake Service (TCP)
    API_PORT = 5000           # API Bridge (Flask)
    
    # ==================== PORT REGISTRY (for firewall management) ====================
    # Each entry: (port, protocol, description, expose_to_network)
    # expose_to_network=False means localhost-only (no firewall rule needed)
    REQUIRED_PORTS = [
        (4433, "udp", "QUIC File Transfer",  True),
        (4434, "udp", "CA Discovery",        True),
        (4435, "tcp", "CA Signing",          True),
        (4436, "udp", "Peer Discovery",      True),
        (4437, "tcp", "Handshake Service",   True),
        (5000, "tcp", "Flask API (local)",   False),
    ]
    
    # ==================== PROTOCOL CONSTANTS ====================
    PEER_DISCOVERY_MSG = b"WHO_IS_PEER"
    PEER_RESPONSE_PREFIX = b"I_AM_PEER"
    CA_DISCOVERY_MSG = b"WHO_IS_CA"
    CA_RESPONSE_PREFIX = b"I_AM_CA"
    
    # ==================== INSTANCE STATE ====================
    _instance: Optional['AppConfig'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Ensure singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize configuration from .env file."""
        if self._initialized:
            return
        
        self._config_lock = threading.RLock()
        self._load_from_env()
        self._initialized = True
    
    def _load_from_env(self) -> None:
        """Load all configuration from .env file (pure Python — no dotenv dep)."""
        # Parse .env and push every key into os.environ (override=True semantics)
        for key, value in self.read_env_file().items():
            os.environ[key] = value
        
        with self._config_lock:
            # Determine app directory
            self._app_dir = Path(__file__).parent.resolve()
            
            # System info
            self.pwd = os.getenv("PWD", os.getcwd())
            self.user = os.getenv("USER", getpass.getuser())
            self.system_type = os.getenv("SYSTEM", platform.system().lower())
            
            # Network configuration
            self.interface = os.getenv("INTERFACE", "")
            self.host = os.getenv("HOST", "")
            self.subnet = os.getenv("SUBNET", "")
            self.gateway = os.getenv("GATEWAY", "")
            self.broadcast = os.getenv("BROADCAST", "")
            self.cidr = os.getenv("CIDR", "24")
            
            # Port (use env or default constant)
            port_str = os.getenv("PORT", str(self.QUIC_PORT))
            self.port = int(port_str) if port_str.isdigit() else self.QUIC_PORT
            
            # Paths
            self.out_dir = os.getenv("OUTDIR", "")
            self.src_dir = os.getenv("SRCDIR", "")
            
            # Certificates
            self.certi = os.getenv("CERTI", os.path.join(self.pwd, "cert.pem"))
            self.key = os.getenv("KEY", os.path.join(self.pwd, "key.pem"))
            self.ca_cert = os.getenv("CA_CERT", os.path.join(self.pwd, "ca_cert.pem"))
            
            # Hosts
            self.dest_host = os.getenv("DEST_HOST", "")
            self.reciv_host = os.getenv("RECIVHOST", "0.0.0.0")
            
            # Installer flag
            self.installer = os.getenv("INSTALLER", "false").lower() == "true"

    # ==================== .env FILE I/O (no dotenv dep) ====================

    def read_env_file(self, env_path: Optional[str] = None) -> Dict[str, str]:
        """
        Parse a .env file into a plain dict WITHOUT loading it into os.environ.
        Handles KEY=value and KEY='value' and KEY="value" formats.
        Replaces dotenv_values() for callers that only need to read values.
        """
        path = env_path or str(_APP_DIR / ".env")
        result: Dict[str, str] = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key:
                        result[key] = val
        except FileNotFoundError:
            pass
        except Exception as exc:
            print(f"[AppConfig] Warning: could not read .env: {exc}")
        return result

    def write_env(self, key: str, value: str, env_path: Optional[str] = None) -> bool:
        """
        Write / update a single key in the .env file (pure file I/O).
        Replaces dotenv's set_key() across the codebase.
        Also updates os.environ immediately.
        """
        return self.write_env_bulk({key: value}, env_path=env_path)

    def write_env_bulk(self, kvdict: Dict[str, str], env_path: Optional[str] = None) -> bool:
        """
        Write / update multiple keys in the .env file atomically.
        Existing keys are updated in-place; new keys are appended.
        Replaces the set_key() loop in startsetup.write_env().
        """
        path = env_path or str(_APP_DIR / ".env")
        try:
            Path(path).touch(exist_ok=True)
            # Read existing lines preserving comments / ordering
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            updated_keys = set()
            new_lines = []
            for raw in lines:
                line = raw.rstrip("\n")
                if "=" in line and not line.strip().startswith("#"):
                    k = line.partition("=")[0].strip()
                    if k in kvdict:
                        new_lines.append(f"{k}='{kvdict[k]}'\n")
                        updated_keys.add(k)
                        continue
                new_lines.append(raw if raw.endswith("\n") else raw + "\n")

            # Append keys that weren't already in the file
            for k, v in kvdict.items():
                if k not in updated_keys:
                    new_lines.append(f"{k}='{v}'\n")

            with open(path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            # Propagate to current process environment
            for k, v in kvdict.items():
                os.environ[k] = str(v)
            return True
        except Exception as exc:
            print(f"[AppConfig] Error writing .env: {exc}")
            return False

    def reload(self) -> None:
        """
        Reload configuration from .env file.
        Thread-safe: use this when you need to refresh config at runtime.
        """
        self._load_from_env()
        print("[AppConfig] Configuration reloaded from .env")
    
    def get_all(self) -> Dict[str, Any]:
        """
        Return all configuration as a dictionary.
        Includes password fetched lazily from ConfigManager (if available).
        """
        # Lazy import to avoid circular imports at module level
        try:
            from config_manager import get_password as _get_pw
            password = _get_pw()
        except Exception:
            password = os.environ.get("PASSWORD")

        with self._config_lock:
            return {
                "host": self.host,
                "port": self.port,
                "certi": self.certi,
                "key": self.key,
                "out_dir": self.out_dir,
                "src_dir": self.src_dir,
                "interface": self.interface,
                "system": self.system_type,
                "pwd": self.pwd,
                "user": self.user,
                "subnet": self.subnet,
                "gateway": self.gateway,
                "broadcast": self.broadcast,
                "cidr": self.cidr,
                "dest_host": self.dest_host,
                "recivhost": self.reciv_host,
                "ca_cert": self.ca_cert,
                "password": password,
            }
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key.
        Provides dict-like access for backward compatibility.
        
        Args:
            key: Configuration key (case-insensitive for common keys)
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        # Map common key variations
        key_map = {
            "host": "host",
            "HOST": "host",
            "port": "port",
            "PORT": "port",
            "certi": "certi",
            "CERTI": "certi",
            "key": "key",
            "KEY": "key",
            "out_dir": "out_dir",
            "OUTDIR": "out_dir",
            "src_dir": "src_dir",
            "SRCDIR": "src_dir",
            "dest_host": "dest_host",
            "DEST_HOST": "dest_host",
            "recivhost": "reciv_host",
            "RECIVHOST": "reciv_host",
            "ca_cert": "ca_cert",
            "CA_CERT": "ca_cert",
            "system": "system_type",
            "SYSTEM": "system_type",
        }
        
        normalized_key = key_map.get(key, key)
        with self._config_lock:
            return getattr(self, normalized_key, default)
    
    @property
    def app_dir(self) -> Path:
        """Get the application directory path."""
        return self._app_dir


# ==================== SINGLETON ACCESS ====================

_config_instance: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """
    Get the global AppConfig singleton instance.
    
    This is the primary way to access configuration throughout the application.
    Thread-safe and lazy-initialized on first call.
    
    Returns:
        AppConfig singleton instance
        
    Usage:
        from app_config import get_config
        config = get_config()
        print(config.host, config.QUIC_PORT)
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = AppConfig()
    return _config_instance


def reload_config() -> None:
    """
    Reload configuration from .env file.
    Convenience function that calls get_config().reload().
    """
    get_config().reload()


# ==================== BACKWARD COMPATIBILITY ====================

def load_env_vars() -> Dict[str, Any]:
    """
    Load environment variables and return as dictionary.
    
    DEPRECATED: Use get_config().get_all() instead.
    This function is kept for backward compatibility.
    """
    return get_config().get_all()


if __name__ == "__main__":
    # Self-test
    config = get_config()
    print("AppConfig Self-Test")
    print("=" * 40)
    print(f"App Directory: {config.app_dir}")
    print(f"QUIC Port: {config.QUIC_PORT}")
    print(f"Peer Discovery Port: {config.PEER_DISCOVERY_PORT}")
    print(f"Host: {config.host}")
    print(f"System: {config.system_type}")
    print()
    print("All config:")
    for k, v in config.get_all().items():
        print(f"  {k}: {v}")
