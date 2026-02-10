import 'dart:io';
import 'package:lanfxplorer/core/utils/logger.dart';
import 'package:lanfxplorer/core/constants/path_security.dart';
import 'package:lanfxplorer/data/models/file_item.dart';
import 'package:lanfxplorer/data/services/api_service.dart';
import 'package:flutter/foundation.dart';

class FileSystemProvider extends ChangeNotifier {
  final ApiService? _apiService;

  FileSystemProvider({ApiService? apiService}) : _apiService = apiService;
  List<FileItem> _localFiles = [];
  List<FileItem> _remoteFiles = [];
  String _localCurrentPath = '.'; // Will be converted to absolute on first load
  String _remoteCurrentPath = '.'; // Will be set properly on first load
  String? _remoteHost;
  bool _isLoadingLocal = false;
  bool _isLoadingRemote = false;

  // Root path restriction - set from outDir in environment
  String? _rootPath;

  // Error state for displaying connection/API errors
  String? _localError;
  String? _remoteError;

  List<FileItem> get localFiles => _localFiles;
  List<FileItem> get remoteFiles => _remoteFiles;
  String get localCurrentPath => _localCurrentPath;
  String get remoteCurrentPath => _remoteCurrentPath;
  String? get rootPath => _rootPath;
  bool get isLoadingLocal => _isLoadingLocal;
  bool get isLoadingRemote => _isLoadingRemote;

  List<FileItem> get selectedLocalFiles =>
      _localFiles.where((f) => f.isSelected).toList();
  List<FileItem> get selectedRemoteFiles =>
      _remoteFiles.where((f) => f.isSelected).toList();

  // Error getters
  String? get localError => _localError;
  String? get remoteError => _remoteError;

  /// Set the root path for path restrictions
  void setRootPath(String path) {
    _rootPath = path;
    // Initialize local path to root if not set or if it's the default
    if (_localCurrentPath == '.' || _localCurrentPath == './') {
      _localCurrentPath = path;
    }
    notifyListeners();
  }

  /// Check if we're at the local root path (cannot navigate up further)
  bool get isAtLocalRoot {
    // Use Lanfxplorer root as the minimum boundary
    final lanfxRoot = getLanfxplorerRoot().replaceAll('\\', '/');
    final normalizedCurrent = _localCurrentPath.replaceAll('\\', '/');
    return normalizedCurrent == lanfxRoot;
  }

  /// Check if we're at the remote root path
  bool get isAtRemoteRoot {
    // Use Lanfxplorer root as the minimum boundary
    final lanfxRoot = getLanfxplorerRoot().replaceAll('\\', '/');
    final normalizedCurrent = _remoteCurrentPath.replaceAll('\\', '/');
    return normalizedCurrent == lanfxRoot;
  }

  Future<void> loadLocalFiles([String? path]) async {
    _isLoadingLocal = true;
    _localError = null; // Clear previous error
    notifyListeners();

    if (path != null) {
      // Ensure path is absolute
      if (path == '.' || path == './') {
        _localCurrentPath = Directory.current.path;
      } else if (!path.startsWith('/')) {
        _localCurrentPath = Directory(path).absolute.path;
      } else {
        _localCurrentPath = path;
      }
    }

    try {
      if (_apiService != null) {
        AppLogger.info('Loading local files from $_localCurrentPath');

        _localFiles = await _apiService.getFiles(
          _localCurrentPath,
        );

        // If we got files, clear any error
        _localError = null;
      } else {
        _localFiles = [];
        _localError =
            'Backend not connected. Check if api_bridge.py is running.';
      }
    } catch (e, stack) {
      AppLogger.error(
        'Failed to load local files',
        error: e,
        stackTrace: stack,
      );
      _localFiles = [];
      _localError =
          'Peer not up or backend disconnected.\nCheck the status and network.';
    }

    _isLoadingLocal = false;
    notifyListeners();
  }

  Future<void> loadRemoteFiles([String? path, String? host]) async {
    _isLoadingRemote = true;
    _remoteError = null; // Clear previous error
    notifyListeners();

    if (host != null) _remoteHost = host;

    // If path is '.' or empty, fetch the remote's default path first
    if (path == null || path == '.' || path == './' || path.isEmpty) {
      if (_apiService != null && _remoteHost != null) {
        try {
          final defaultPath =
              await _apiService.getDefaultPath(remoteHost: _remoteHost);
          if (defaultPath != null && defaultPath.isNotEmpty) {
            _remoteCurrentPath = defaultPath;
            AppLogger.info('Remote default path resolved to: $defaultPath');
          } else {
            // Fallback to local Lanfxplorer path format
            _remoteCurrentPath = getLanfxplorerRoot();
            AppLogger.warning(
                'Could not get remote default path, using local format');
          }
        } catch (e) {
          AppLogger.error('Failed to get remote default path: $e');
          _remoteCurrentPath = getLanfxplorerRoot();
        }
      } else if (path != null) {
        _remoteCurrentPath = path;
      }
    } else {
      _remoteCurrentPath = path;
    }

    try {
      if (_apiService != null) {
        _remoteFiles = await _apiService.getFiles(
          _remoteCurrentPath,
          remoteHost: _remoteHost,
        );
        // Update path from the first file's parent if available (to get absolute path)
        if (_remoteFiles.isNotEmpty &&
            (_remoteCurrentPath == '.' || _remoteCurrentPath == './')) {
          final firstPath = _remoteFiles.first.path;
          final parentDir = firstPath.substring(0, firstPath.lastIndexOf('/'));
          if (parentDir.isNotEmpty) {
            _remoteCurrentPath = parentDir;
          }
        }
        // Clear error on success
        _remoteError = null;
      } else {
        _remoteFiles = [];
        _remoteError =
            'Backend not connected. Check if api_bridge.py is running.';
      }
    } catch (e, stack) {
      AppLogger.error('Failed to load remote files',
          error: e, stackTrace: stack);
      _remoteFiles = [];
      _remoteError =
          'Peer not up or backend disconnected.\nCheck the status and network.';
    }

    _isLoadingRemote = false;
    notifyListeners();
  }

  void toggleLocalFileSelection(int index) {
    _localFiles[index] =
        _localFiles[index].copyWith(isSelected: !_localFiles[index].isSelected);
    notifyListeners();
  }

  void toggleRemoteFileSelection(int index) {
    _remoteFiles[index] = _remoteFiles[index]
        .copyWith(isSelected: !_remoteFiles[index].isSelected);
    notifyListeners();
  }

  void selectAllLocal() {
    _localFiles = _localFiles.map((f) => f.copyWith(isSelected: true)).toList();
    notifyListeners();
  }

  void selectAllRemote() {
    _remoteFiles =
        _remoteFiles.map((f) => f.copyWith(isSelected: true)).toList();
    notifyListeners();
  }

  void clearLocalSelection() {
    _localFiles =
        _localFiles.map((f) => f.copyWith(isSelected: false)).toList();
    notifyListeners();
  }

  void clearRemoteSelection() {
    _remoteFiles =
        _remoteFiles.map((f) => f.copyWith(isSelected: false)).toList();
    notifyListeners();
  }

  Future<void> addExternalFilesToLocal(List<String> filePaths) async {
    int copiedCount = 0;
    for (final sourcePath in filePaths) {
      try {
        final name = sourcePath.split('/').last;
        final destPath = '$_localCurrentPath/$name';
        final isDir = FileSystemEntity.isDirectorySync(sourcePath);

        if (isDir) {
          // Copy directory recursively
          await _copyDirectory(Directory(sourcePath), Directory(destPath));
        } else {
          // Copy file
          await File(sourcePath).copy(destPath);
        }

        // Get file info for the copied file
        int? fileSize;
        if (!isDir) {
          try {
            fileSize = File(destPath).lengthSync();
          } catch (_) {}
        }

        final file = FileItem(
          name: name,
          path: destPath,
          isDirectory: isDir,
          size: fileSize,
          modified: DateTime.now(),
          isSelected: true, // Auto-select for immediate transfer
        );
        _localFiles.add(file);
        copiedCount++;
        AppLogger.info('Copied $sourcePath to $destPath');
      } catch (e) {
        AppLogger.error('Failed to copy $sourcePath: $e');
      }
    }
    notifyListeners();
    AppLogger.info('Copied $copiedCount external files to $_localCurrentPath');
  }

  /// Recursively copy a directory
  Future<void> _copyDirectory(Directory source, Directory destination) async {
    if (!await destination.exists()) {
      await destination.create(recursive: true);
    }
    await for (final entity in source.list(recursive: false)) {
      final newPath = '${destination.path}/${entity.path.split('/').last}';
      if (entity is File) {
        await entity.copy(newPath);
      } else if (entity is Directory) {
        await _copyDirectory(entity, Directory(newPath));
      }
    }
  }

  void navigateLocalUp() {
    // Check if at root boundary - cannot navigate up
    if (isAtLocalRoot) return;
    if (_localCurrentPath == '/') return;

    final dir = Directory(_localCurrentPath).parent;
    _localCurrentPath = dir.path.isEmpty ? '/' : dir.path;
    loadLocalFiles(_localCurrentPath);
  }

  void navigateRemoteUp() {
    // Check if at root boundary - cannot navigate up
    if (isAtRemoteRoot) return;
    if (_remoteCurrentPath != '/') {
      final parts = _remoteCurrentPath.split('/');
      parts.removeLast();
      _remoteCurrentPath = parts.join('/');
      if (_remoteCurrentPath.isEmpty) _remoteCurrentPath = '/';
      loadRemoteFiles(_remoteCurrentPath);
    }
  }

  /// Create a new empty file in the current directory
  Future<bool> createFileInDir(String name, {required bool isLocal}) async {
    if (_apiService == null) return false;
    final currentPath = isLocal ? _localCurrentPath : _remoteCurrentPath;
    final fullPath = '$currentPath/$name';
    final remoteHost = isLocal ? null : _remoteHost;

    final success =
        await _apiService.createFile(fullPath, remoteHost: remoteHost);
    if (success) {
      if (isLocal) {
        await loadLocalFiles();
      } else {
        await loadRemoteFiles();
      }
    }
    return success;
  }

  /// Create a new folder in the current directory
  Future<bool> createFolderInDir(String name, {required bool isLocal}) async {
    if (_apiService == null) return false;
    final currentPath = isLocal ? _localCurrentPath : _remoteCurrentPath;
    final fullPath = '$currentPath/$name';
    final remoteHost = isLocal ? null : _remoteHost;

    final success =
        await _apiService.createFolder(fullPath, remoteHost: remoteHost);
    if (success) {
      if (isLocal) {
        await loadLocalFiles();
      } else {
        await loadRemoteFiles();
      }
    }
    return success;
  }

  /// Delete a file or folder
  Future<bool> deleteFileItem(String path, {required bool isLocal}) async {
    if (_apiService == null) return false;
    final remoteHost = isLocal ? null : _remoteHost;

    final success = await _apiService.deleteItem(path, remoteHost: remoteHost);
    if (success) {
      if (isLocal) {
        await loadLocalFiles();
      } else {
        await loadRemoteFiles();
      }
    }
    return success;
  }
}
