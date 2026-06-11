"""
Path Security Module for LANFXplorer

Centralized path validation to restrict access to $HOME/Lanfxplorer directory only.
This module is the single source of truth for path security across the application.

Security Rules:
- Only paths within $HOME/Lanfxplorer are allowed (case-sensitive)
- Path traversal (../) is blocked, including via symlinks (os.path.realpath used)
- Minimum depth of 3 levels required (/home/user/something)
- Maximum depth capped to prevent DoS via deep nested directory creation
"""

import os
import platform
import getpass


# The exact directory name - case-sensitive
LANFXPLORER_DIR_NAME = "Lanfxplorer"

# Path depth limits
# Minimum: 3 parts after split (e.g. ['home', 'user', 'Lanfxplorer'])
MIN_PATH_DEPTH: int = 3
# Maximum: prevents DoS via pathologically deep nested directory creation
MAX_PATH_DEPTH: int = 20



def get_home_directory() -> str:
    """Get the user's home directory in a cross-platform way."""
    if platform.system().lower() == "windows":
        return os.environ.get("USERPROFILE", f"C:\\Users\\{getpass.getuser()}")
    else:
        return os.environ.get("HOME", f"/home/{getpass.getuser()}")


def get_lanfxplorer_root() -> str:
    """
    Get the Lanfxplorer root directory path.
    This is the ONLY directory that users can access.
    
    Returns:
        Absolute path to $HOME/Lanfxplorer
    """
    home = get_home_directory()
    return os.path.join(home, LANFXPLORER_DIR_NAME)


def ensure_lanfxplorer_directory() -> str:
    """
    Ensure the Lanfxplorer directory exists, creating it if necessary.
    
    Returns:
        Absolute path to the Lanfxplorer directory
    """
    root = get_lanfxplorer_root()
    if not os.path.exists(root):
        os.makedirs(root, exist_ok=True)
        print(f"[path_security] Created Lanfxplorer directory: {root}")
    return root


def is_path_at_minimum_depth(path: str) -> bool:
    """
    Check if path is at minimum required depth.
    Paths at /home/user level or above are NOT allowed.
    Must be at least /home/user/something (MIN_PATH_DEPTH levels deep).
    Also rejects paths that are suspiciously deep (> MAX_PATH_DEPTH).
    
    Examples:
        /home/user          -> False (too shallow)
        /home/user/Downloads -> True (ok)
        /home               -> False (too shallow)
        /                   -> False (too shallow)
        
    Args:
        path: Path to check
        
    Returns:
        True if path is at valid depth, False otherwise
    """
    normalized = os.path.normpath(os.path.abspath(path))
    parts = [p for p in normalized.split(os.sep) if p]
    depth = len(parts)
    return MIN_PATH_DEPTH <= depth <= MAX_PATH_DEPTH


def is_path_within_root(requested_path: str, root_path: str = None) -> bool:
    """
    Check if requested_path is within or equal to root_path.
    Handles path traversal AND symlink escapes by using os.path.realpath(),
    which resolves all symlinks before comparison.
    
    Example attack this blocks:
        ~/Lanfxplorer/escape -> /etc/   (symlink)
        normpath would see it as inside root; realpath resolves to /etc/.
    
    Args:
        requested_path: The path being requested
        root_path: The allowed root directory (defaults to Lanfxplorer root)
        
    Returns:
        True if requested_path is within root_path, False otherwise
    """
    if root_path is None:
        root_path = get_lanfxplorer_root()
    
    # For paths that don't exist yet (e.g. a new incoming file), resolve the
    # *parent* directory (which must exist) and re-append the filename so that
    # realpath() can follow all symlinks up to the deepest existing ancestor.
    def _safe_realpath(p: str) -> str:
        p_abs = os.path.abspath(p)
        if os.path.exists(p_abs):
            return os.path.realpath(p_abs)
        parent = os.path.realpath(os.path.dirname(p_abs))
        return os.path.join(parent, os.path.basename(p_abs))

    requested_real = _safe_realpath(requested_path)
    root_real      = _safe_realpath(root_path)
    
    if requested_real == root_real:
        return True
    return requested_real.startswith(root_real + os.sep)


def validate_path_access(path: str) -> tuple:
    """
    Validate that a path is accessible under the current restrictions.
    
    This is the main validation function that should be used throughout
    the application to check if a path is allowed.
    
    Args:
        path: Path to validate
        
    Returns:
        (is_valid, error_message) tuple
        - is_valid: True if path is allowed, False otherwise
        - error_message: Empty string if valid, error description otherwise
    """
    root_path = get_lanfxplorer_root()
    
    # First check: Is the ROOT_PATH itself at a safe depth?
    if not is_path_at_minimum_depth(root_path):
        return False, f"Root path '{root_path}' is too shallow. Must be below /home/user level."
    
    # Second check: Is the requested path within the root?
    if not is_path_within_root(path, root_path):
        return False, f"Access denied: Path '{path}' is outside allowed directory '{root_path}'"
    
    return True, ""


def get_default_dirs() -> dict:
    """
    Get the default directory paths for the application.
    All directories are set to the Lanfxplorer root.
    
    Returns:
        dict with 'out_dir', 'src_dir', 'pwd' keys
    """
    root = ensure_lanfxplorer_directory()
    return {
        "out_dir": root,
        "src_dir": root,
        "pwd": root,
    }


def sanitize_path(path: str) -> str:
    """
    Sanitize a path by resolving it and ensuring it's within the allowed root.
    
    Args:
        path: Path to sanitize
        
    Returns:
        Sanitized absolute path if valid
        
    Raises:
        PermissionError: If path is outside allowed root
    """
    is_valid, error_msg = validate_path_access(path)
    if not is_valid:
        raise PermissionError(error_msg)
    
    return os.path.normpath(os.path.abspath(path))


# Quick validation functions for common patterns
def validate_dest_dir(dest_dir: str) -> tuple:
    """
    Validate a destination directory for file transfers.
    
    Args:
        dest_dir: Destination directory path
        
    Returns:
        (is_valid, error_message) tuple
    """
    if not dest_dir:
        return True, ""  # No dest_dir specified is OK (uses default)
    
    return validate_path_access(dest_dir)


def validate_file_path(file_path: str) -> tuple:
    """
    Validate a file path for read/write operations.
    
    Args:
        file_path: File path to validate
        
    Returns:
        (is_valid, error_message) tuple
    """
    return validate_path_access(file_path)


if __name__ == "__main__":
    # Self-test
    print(f"Lanfxplorer root: {get_lanfxplorer_root()}")
    
    test_paths = [
        get_lanfxplorer_root(),
        os.path.join(get_lanfxplorer_root(), "test"),
        "/",
        "/home",
        os.path.expanduser("~"),
        os.path.expanduser("~/Downloads"),
        os.path.join(get_lanfxplorer_root(), ".."),
        os.path.join(get_lanfxplorer_root(), "../other"),
    ]
    
    print("\nPath validation tests:")
    for p in test_paths:
        is_valid, err = validate_path_access(p)
        status = "✓ ALLOWED" if is_valid else "✗ BLOCKED"
        print(f"  {status}: {p}")
        if err:
            print(f"           {err}")
