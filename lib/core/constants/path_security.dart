import 'dart:io';

/// Path Security Constants for LANFXplorer
///
/// Centralized path validation to restrict access to $HOME/Lanfxplorer directory.
/// This mirrors the Python path_security.py module for consistency.

/// The exact directory name - case-sensitive
const String lanfxplorerDirName = 'Lanfxplorer';

/// Get the user's home directory in a cross-platform way
String getHomeDirectory() {
  if (Platform.isWindows) {
    return Platform.environment['USERPROFILE'] ?? 'C:\\Users';
  } else {
    return Platform.environment['HOME'] ?? '/home';
  }
}

/// Get the Lanfxplorer root directory path.
/// This is the ONLY directory that users can access.
String getLanfxplorerRoot() {
  final home = getHomeDirectory();
  return '$home${Platform.pathSeparator}$lanfxplorerDirName';
}

/// Check if a path is within the allowed Lanfxplorer directory.
/// Handles path traversal attempts and normalizes paths for comparison.
bool isPathAllowed(String path) {
  final allowedRoot = getLanfxplorerRoot();

  // Normalize paths for comparison (handle both / and \ separators)
  final normalizedPath = path.replaceAll('\\', '/').replaceAll('//', '/');
  final normalizedRoot = allowedRoot.replaceAll('\\', '/');

  // Path must be exactly the root or start with root + separator
  return normalizedPath == normalizedRoot ||
      normalizedPath.startsWith('$normalizedRoot/');
}

/// Validate that a path is accessible under the current restrictions.
/// Returns (isValid, errorMessage) as a record.
(bool, String) validatePathAccess(String path) {
  final root = getLanfxplorerRoot();

  if (!isPathAllowed(path)) {
    return (
      false,
      "Access denied: Path '$path' is outside allowed directory '$root'"
    );
  }

  return (true, '');
}

/// Ensure the Lanfxplorer directory exists, creating it if necessary.
Future<String> ensureLanfxplorerDirectory() async {
  final root = getLanfxplorerRoot();
  final dir = Directory(root);

  if (!await dir.exists()) {
    await dir.create(recursive: true);
  }

  return root;
}
