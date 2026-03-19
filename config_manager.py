"""
LANFXplorer Config Manager

Unified configuration management that:
- Stores sensitive data (PASSWORD) in OS keyring
- Stores non-sensitive data (HOST, PORT, etc.) in .env file
- Provides cross-platform support (Linux, Windows, macOS)
"""

import os
import platform
from pathlib import Path
from typing import Optional

# Lazy import keyring to allow graceful fallback
_keyring = None

def _get_keyring():
    """Lazy load keyring module with automatic backend selection for Linux.
    
    On Windows/macOS, keyring works out-of-the-box.
    On Linux, keyring needs a D-Bus SecretService backend (GNOME Keyring, KWallet).
    If none is available (headless/minimal distros), fall back to file-based storage.
    """
    global _keyring
    if _keyring is None:
        try:
            import keyring
            
            # On Linux, verify the backend is actually usable
            if platform.system().lower().startswith("linux"):
                try:
                    backend = keyring.get_keyring()
                    backend_name = type(backend).__name__
                    
                    # Check if backend is a known non-functional placeholder
                    if backend_name in ("Fail",) or "fail" in backend_name.lower():
                        raise RuntimeError(f"Non-functional backend: {backend_name}")
                    
                    # Quick smoke test: try a harmless read to confirm the backend works
                    keyring.get_password("LANFXplorer_probe", "_probe_")
                    
                except Exception:
                    # D-Bus SecretService not available — use file-based fallback
                    try:
                        from keyrings.alt.file import PlaintextKeyring
                        keyring.set_keyring(PlaintextKeyring())
                        print("[config] Using file-based keyring backend (no D-Bus secret service found)")
                    except ImportError:
                        print("[config] Warning: No keyring backend available, install keyrings.alt")
                        _keyring = False
                        return None
            
            _keyring = keyring
        except ImportError:
            _keyring = False  # Mark as unavailable
    return _keyring if _keyring else None


class ConfigManager:
    """
    Manages application configuration with secure storage for secrets.
    
    - Passwords are stored in the OS keyring (GNOME Keyring, Windows Credential Manager, etc.)
    - Non-sensitive config is stored in .env file
    """
    
    SERVICE_NAME = "LANFXplorer"
    PASSWORD_KEY = "password"
    
    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize the config manager.
        
        Args:
            env_file: Path to .env file. Defaults to .env in current directory.
        """
        self.env_file = env_file or os.path.join(os.getcwd(), ".env")
        self._system = platform.system().lower()
    
    # =========================================================================
    # Password Management (Keyring)
    # =========================================================================
    
    def get_password(self) -> Optional[str]:
        """
        Get password from OS keyring.
        
        Returns:
            The stored password, or None if not set.
        """
        keyring = _get_keyring()
        if keyring:
            try:
                return keyring.get_password(self.SERVICE_NAME, self.PASSWORD_KEY)
            except Exception as e:
                print(f"[config] Warning: Could not read from keyring: {e}")
        
        # Fallback: Check environment variable
        return os.environ.get("PASSWORD")
    
    def set_password(self, password: str) -> bool:
        """
        Store password in OS keyring.
        
        Args:
            password: The password to store.
            
        Returns:
            True if successful, False otherwise.
        """
        keyring = _get_keyring()
        if keyring:
            try:
                keyring.set_password(self.SERVICE_NAME, self.PASSWORD_KEY, password)
                # Also set in environment for current session
                os.environ["PASSWORD"] = password
                return True
            except Exception as e:
                print(f"[config] Warning: Could not write to keyring: {e}")
        
        # Fallback: Set environment variable only (not persistent)
        os.environ["PASSWORD"] = password
        print("[config] Warning: Password stored in memory only (keyring unavailable)")
        return False
    
    def delete_password(self) -> bool:
        """
        Delete password from OS keyring.
        
        Returns:
            True if successful, False otherwise.
        """
        keyring = _get_keyring()
        if keyring:
            try:
                keyring.delete_password(self.SERVICE_NAME, self.PASSWORD_KEY)
            except keyring.errors.PasswordDeleteError:
                pass  # Password didn't exist
            except Exception as e:
                print(f"[config] Warning: Could not delete from keyring: {e}")
                return False
        
        # Clear from environment
        os.environ.pop("PASSWORD", None)
        return True
    
    def has_password(self) -> bool:
        """Check if a password is configured."""
        return self.get_password() is not None
    
    # =========================================================================
    # Config File Management (.env)
    # =========================================================================
    
    def get_config_value(self, key: str, default: str = "") -> str:
        """
        Get a configuration value from .env file.
        """
        # First check environment (allows runtime overrides)
        if key in os.environ:
            return os.environ[key]

        # Then check .env file via AppConfig's pure-Python reader
        from app_config import get_config
        return get_config().read_env_file().get(key, default)
    
    def set_config_value(self, key: str, value: str) -> bool:
        """
        Set a configuration value in .env file.
        """
        # Don't store PASSWORD in .env - use keyring instead
        if key.upper() == "PASSWORD":
            return self.set_password(value)

        from app_config import get_config
        return get_config().write_env(key, str(value), env_path=self.env_file)
    
    # =========================================================================
    # Migration
    # =========================================================================
    
    def migrate_password_from_env(self) -> bool:
        """
        Migrate PASSWORD from .env file to keyring (one-time operation).
        """
        try:
            from app_config import get_config
            cfg = get_config()
            env_password = cfg.read_env_file(self.env_file).get("PASSWORD")

            if env_password:
                if self.set_password(env_password):
                    self._remove_key_from_env("PASSWORD")
                    print("[config] Migrated PASSWORD from .env to secure keyring")
                    return True
        except Exception as e:
            print(f"[config] Migration error: {e}")

        return False
    
    def _remove_key_from_env(self, key: str):
        """Remove a key from the .env file."""
        if not os.path.exists(self.env_file):
            return
        
        lines = []
        with open(self.env_file, "r") as f:
            for line in f:
                if not line.strip().startswith(f"{key}="):
                    lines.append(line)
        
        with open(self.env_file, "w") as f:
            f.writelines(lines)
    
    # =========================================================================
    # Unified Config Loading (Backward Compatible)
    # =========================================================================
    
    def load_all_config(self) -> dict:
        """
        Load all configuration (env + password).
        Maintains backward compatibility with load_env_vars() return format.
        """
        from app_config import get_config
        get_config().reload()

        # Run migration on first load
        self.migrate_password_from_env()

        password = self.get_password()
        if password:
            os.environ["PASSWORD"] = password

        return {"password": password}


# Module-level singleton for convenience
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global ConfigManager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


# Convenience functions
def get_password() -> Optional[str]:
    """Get password from secure storage."""
    return get_config_manager().get_password()


def set_password(password: str) -> bool:
    """Set password in secure storage."""
    return get_config_manager().set_password(password)


def delete_password() -> bool:
    """Delete password from secure storage (logout)."""
    return get_config_manager().delete_password()


def has_password() -> bool:
    """Check if password is configured."""
    return get_config_manager().has_password()
