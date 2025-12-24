"""
Unit tests for path_security module.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from path_security import (
    get_lanfxplorer_root,
    is_path_at_minimum_depth,
    is_path_within_root,
    validate_path_access,
    get_home_directory,
    LANFXPLORER_DIR_NAME,
)


class TestPathSecurity(unittest.TestCase):
    
    def test_lanfxplorer_root_returns_correct_path(self):
        """Test that the root path is correctly constructed."""
        root = get_lanfxplorer_root()
        home = get_home_directory()
        expected = os.path.join(home, LANFXPLORER_DIR_NAME)
        self.assertEqual(root, expected)
        self.assertTrue(root.endswith("Lanfxplorer"))
    
    def test_allowed_paths(self):
        """Test that paths within Lanfxplorer are allowed."""
        root = get_lanfxplorer_root()
        
        # Root itself should be allowed
        is_valid, _ = validate_path_access(root)
        self.assertTrue(is_valid, f"Root path {root} should be allowed")
        
        # Subdirectories should be allowed
        subdir = os.path.join(root, "subdir")
        is_valid, _ = validate_path_access(subdir)
        self.assertTrue(is_valid, f"Subdir {subdir} should be allowed")
        
        # Nested subdirectories should be allowed
        nested = os.path.join(root, "a", "b", "c")
        is_valid, _ = validate_path_access(nested)
        self.assertTrue(is_valid, f"Nested {nested} should be allowed")
    
    def test_blocked_paths(self):
        """Test that paths outside Lanfxplorer are blocked."""
        blocked_paths = [
            "/",
            "/home",
            get_home_directory(),
            os.path.join(get_home_directory(), "Downloads"),
            "/tmp",
            "/etc",
        ]
        
        for path in blocked_paths:
            is_valid, error = validate_path_access(path)
            self.assertFalse(is_valid, f"Path {path} should be BLOCKED")
            self.assertIn("Access denied", error)
    
    def test_path_traversal_blocked(self):
        """Test that path traversal attacks are blocked."""
        root = get_lanfxplorer_root()
        
        traversal_attempts = [
            os.path.join(root, ".."),
            os.path.join(root, "..", "other"),
            os.path.join(root, "subdir", "..", "..", "outside"),
        ]
        
        for path in traversal_attempts:
            is_valid, error = validate_path_access(path)
            self.assertFalse(is_valid, f"Traversal path {path} should be BLOCKED")
    
    def test_case_sensitivity(self):
        """Test that the directory name is case-sensitive."""
        home = get_home_directory()
        
        # Correct case should be allowed
        correct = os.path.join(home, "Lanfxplorer")
        is_valid, _ = validate_path_access(correct)
        self.assertTrue(is_valid)
        
        # Wrong cases should be blocked (unless happens to be the same path)
        wrong_cases = [
            os.path.join(home, "lanfxplorer"),
            os.path.join(home, "LANFXPLORER"),
            os.path.join(home, "LanFXplorer"),
        ]
        
        for path in wrong_cases:
            is_valid, _ = validate_path_access(path)
            # Only expect blocked if it's actually different from correct case
            if path != correct:
                self.assertFalse(is_valid, f"Wrong case {path} should be BLOCKED")
    
    def test_minimum_depth_check(self):
        """Test minimum depth validation."""
        self.assertFalse(is_path_at_minimum_depth("/"))
        self.assertFalse(is_path_at_minimum_depth("/home"))
        self.assertFalse(is_path_at_minimum_depth("/home/user"))
        self.assertTrue(is_path_at_minimum_depth("/home/user/something"))
        self.assertTrue(is_path_at_minimum_depth("/home/user/a/b"))


if __name__ == '__main__':
    unittest.main(verbosity=2)
