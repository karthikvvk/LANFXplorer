import 'dart:io';
import 'package:files/core/utils/logger.dart';
import 'package:files/data/models/file_item.dart';
import 'package:files/data/services/api_service.dart';
import 'package:flutter/foundation.dart';

class FileSystemProvider extends ChangeNotifier {
  final ApiService? _apiService;

  FileSystemProvider({ApiService? apiService}) : _apiService = apiService;
  List<FileItem> _localFiles = [];
  List<FileItem> _remoteFiles = [];
  String _localCurrentPath = '/';
  String _remoteCurrentPath = '/';
  String? _remoteHost;
  bool _isLoadingLocal = false;
  bool _isLoadingRemote = false;

  List<FileItem> get localFiles => _localFiles;
  List<FileItem> get remoteFiles => _remoteFiles;
  String get localCurrentPath => _localCurrentPath;
  String get remoteCurrentPath => _remoteCurrentPath;
  bool get isLoadingLocal => _isLoadingLocal;
  bool get isLoadingRemote => _isLoadingRemote;

  List<FileItem> get selectedLocalFiles =>
      _localFiles.where((f) => f.isSelected).toList();
  List<FileItem> get selectedRemoteFiles =>
      _remoteFiles.where((f) => f.isSelected).toList();

  Future<void> loadLocalFiles([String? path]) async {
    _isLoadingLocal = true;
    notifyListeners();

    if (path != null) {
      _localCurrentPath = path;
    }

    try {
      if (_apiService != null) {
        AppLogger.info('Loading local files from $_localCurrentPath');

        _localFiles = await _apiService.getFiles(
          _localCurrentPath,
        );
      } else {
        _localFiles = [];
      }
    } catch (e, stack) {
      AppLogger.error(
        'Failed to load local files',
        error: e,
        stackTrace: stack,
      );
      _localFiles = [];
    }

    _isLoadingLocal = false;
    notifyListeners();
  }

  Future<void> loadRemoteFiles([String? path, String? host]) async {
    _isLoadingRemote = true;
    notifyListeners();

    if (path != null) _remoteCurrentPath = path;

    try {
      if (_apiService != null) {
        _remoteFiles = await _apiService.getFiles(
          _remoteCurrentPath,
          remoteHost: _remoteHost,
        );
      }
    } catch (e, stack) {
      AppLogger.error('Failed to load remote files',
          error: e, stackTrace: stack);
      _remoteFiles = [];
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

  void addExternalFilesToLocal(List<String> filePaths) {
    for (final path in filePaths) {
      final name = path.split('/').last;
      final file = FileItem(
        name: name,
        path: path,
        isDirectory: false,
        modified: DateTime.now(),
      );
      _localFiles.add(file);
    }
    notifyListeners();
    AppLogger.info('Added ${filePaths.length} external files to local');
  }

  void navigateLocalUp() {
    if (_localCurrentPath == '/') return;

    final dir = Directory(_localCurrentPath).parent;
    _localCurrentPath = dir.path.isEmpty ? '/' : dir.path;
    loadLocalFiles(_localCurrentPath);
  }

  void navigateRemoteUp() {
    if (_remoteCurrentPath != '/') {
      final parts = _remoteCurrentPath.split('/');
      parts.removeLast();
      _remoteCurrentPath = parts.join('/');
      if (_remoteCurrentPath.isEmpty) _remoteCurrentPath = '/';
      loadRemoteFiles(_remoteCurrentPath);
    }
  }
}
