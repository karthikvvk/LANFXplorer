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

from dotenv import load_dotenv


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
        """Load all configuration from .env file."""
        # Reload .env file (override=True ensures fresh values)
        load_dotenv(override=True)
        
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
        This maintains backward compatibility with load_env_vars() return format.
        
        Returns:
            Dictionary with all configuration values.
        """
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
