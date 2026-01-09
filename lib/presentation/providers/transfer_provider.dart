import 'dart:convert';
import 'package:lanfxplorer/core/constants/enums.dart';
import 'package:lanfxplorer/core/utils/logger.dart';
import 'package:lanfxplorer/data/models/file_item.dart';
import 'package:lanfxplorer/data/models/transfer_task.dart';
import 'package:lanfxplorer/data/services/api_service.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

class TransferProvider extends ChangeNotifier {
  final ApiService _apiService;
  static const String _tasksKey = 'transfer_history';
  static const int _maxHistorySize = 50;

  final List<TransferTask> _tasks = [];
  final _uuid = const Uuid();

  TransferProvider(this._apiService) {
    _loadHistory();
  }

  Future<void> _loadHistory() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final json = prefs.getString(_tasksKey);
      if (json != null) {
        final List<dynamic> decoded = jsonDecode(json);
        _tasks.addAll(decoded.map((e) => TransferTask.fromJson(e)));
        notifyListeners();
      }
    } catch (e) {
      AppLogger.error('Failed to load transfer history', error: e);
    }
  }

  Future<void> _saveHistory() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      // Keep only the most recent tasks
      while (_tasks.length > _maxHistorySize) {
        _tasks.removeAt(0);
      }
      final json = jsonEncode(_tasks.map((t) => t.toJson()).toList());
      await prefs.setString(_tasksKey, json);
    } catch (e) {
      AppLogger.error('Failed to save transfer history', error: e);
    }
  }

  List<TransferTask> get tasks => List.unmodifiable(_tasks);

  List<TransferTask> get activeTasks => _tasks
      .where((t) =>
          t.status == TransferStatus.inProgress ||
          t.status == TransferStatus.failed)
      .toList();

  List<TransferTask> get completedTasks =>
      _tasks.where((t) => t.status == TransferStatus.completed).toList();

  bool get hasActiveTasks => activeTasks.isNotEmpty;

  // ---------------- SEND ----------------
  Future<bool> sendFiles(String destinationId, List<FileItem> files,
      {String? destDir}) async {
    final taskId = _uuid.v4();
    final paths = files.map((f) => f.path).toList();

    _tasks.add(
      TransferTask(
        id: taskId,
        files: paths,
        destinationMachine: destinationId,
        direction: TransferDirection.send,
        status: TransferStatus.inProgress,
        progress: 0.0,
        createdAt: DateTime.now(),
      ),
    );
    notifyListeners();

    try {
      // Initiate the transfer - this returns immediately with a backend task_id
      final result =
          await _apiService.sendFiles(destinationId, paths, destDir: destDir);

      AppLogger.info(
          'sendFiles result: taskId=${result?.taskId}, status=${result?.status}');

      if (result == null) {
        AppLogger.error('sendFiles returned null result');
        _updateTask(taskId, TransferStatus.failed, 0.0,
            errorMessage: 'Failed to initiate transfer');
        return false;
      }

      final backendTaskId = result.taskId;

      // Validate taskId
      if (backendTaskId.isEmpty) {
        AppLogger.error('Backend returned empty task_id');
        _updateTask(taskId, TransferStatus.failed, 0.0,
            errorMessage: 'Server returned invalid task ID');
        return false;
      }

      // Poll for progress - first poll is immediate
      int pollAttempts = 0;
      const maxPollAttempts = 600; // 5 minutes max
      int pollIntervalMs = 500; // Start with 500ms, adjust after first poll

      while (pollAttempts < maxPollAttempts) {
        // First poll is immediate (no delay), then use calculated interval
        if (pollAttempts > 0) {
          await Future.delayed(Duration(milliseconds: pollIntervalMs));
        }
        pollAttempts++;

        final status = await _apiService.getTransferStatus(backendTaskId);
        if (status == null) {
          // Polling failed, wait and retry
          if (pollAttempts > 10) {
            AppLogger.warning('Polling failed, retrying...');
          }
          await Future.delayed(const Duration(milliseconds: 500));
          continue;
        }

        // On first successful poll, adjust interval based on file size
        // Larger files = slower progress = less frequent polls
        if (pollAttempts == 1 && status.totalSize > 0) {
          // Calculate poll interval: ~1 second per 10MB, min 500ms, max 2000ms
          final sizeMb = status.totalSize / (1024 * 1024);
          pollIntervalMs = (sizeMb * 100).clamp(500, 2000).toInt();
          AppLogger.info(
              'Poll interval set to ${pollIntervalMs}ms for ${sizeMb.toStringAsFixed(1)}MB file');
        }

        // Update local task with progress
        _updateTask(taskId, TransferStatus.inProgress, status.progress);

        if (status.isCompleted) {
          _updateTask(taskId, TransferStatus.completed, 1.0);
          return true;
        } else if (status.isFailed) {
          _updateTask(taskId, TransferStatus.failed, status.progress,
              errorMessage: status.error ?? 'Transfer failed');
          return false;
        }
      }

      // Timeout after max attempts
      _updateTask(taskId, TransferStatus.failed, 0.0,
          errorMessage: 'Transfer timed out');
      return false;
    } catch (e, s) {
      AppLogger.error('Send task error', error: e, stackTrace: s);
      _updateTask(taskId, TransferStatus.failed, 0.0,
          errorMessage: e.toString());
      return false;
    }
  }

  // ---------------- RECEIVE ----------------
  Future<bool> fetchFiles(String sourceId, List<FileItem> files,
      {String? destDir}) async {
    final taskId = _uuid.v4();
    final paths = files.map((f) => f.path).toList();

    _tasks.add(
      TransferTask(
        id: taskId,
        files: paths,
        destinationMachine: sourceId,
        direction: TransferDirection.receive,
        status: TransferStatus.inProgress,
        progress: 0.0,
        createdAt: DateTime.now(),
      ),
    );
    notifyListeners();

    try {
      // Initiate the fetch - this asks the remote to send files to us
      // Returns immediately with the remote's task_id
      final result =
          await _apiService.fetchFiles(sourceId, paths, destDir: destDir);

      AppLogger.info(
          'fetchFiles result: taskId=${result?.taskId}, status=${result?.status}');

      if (result == null) {
        AppLogger.error('fetchFiles returned null result');
        _updateTask(taskId, TransferStatus.failed, 0.0,
            errorMessage: 'Failed to initiate fetch');
        return false;
      }

      final backendTaskId = result.taskId;

      // Validate taskId
      if (backendTaskId.isEmpty) {
        AppLogger.error('Backend returned empty task_id');
        _updateTask(taskId, TransferStatus.failed, 0.0,
            errorMessage: 'Server returned invalid task ID');
        return false;
      }

      // Poll for progress - same logic as sendFiles
      int pollAttempts = 0;
      const maxPollAttempts = 600; // 5 minutes max
      int pollIntervalMs = 500; // Start with 500ms, adjust after first poll

      while (pollAttempts < maxPollAttempts) {
        // First poll is immediate (no delay), then use calculated interval
        if (pollAttempts > 0) {
          await Future.delayed(Duration(milliseconds: pollIntervalMs));
        }
        pollAttempts++;

        final status = await _apiService.getTransferStatus(backendTaskId);
        if (status == null) {
          // Polling failed, wait and retry
          if (pollAttempts > 10) {
            AppLogger.warning('Polling failed, retrying...');
          }
          await Future.delayed(const Duration(milliseconds: 500));
          continue;
        }

        // On first successful poll, adjust interval based on file size
        if (pollAttempts == 1 && status.totalSize > 0) {
          final sizeMb = status.totalSize / (1024 * 1024);
          pollIntervalMs = (sizeMb * 100).clamp(500, 2000).toInt();
          AppLogger.info(
              'Poll interval set to ${pollIntervalMs}ms for ${sizeMb.toStringAsFixed(1)}MB file');
        }

        // Update local task with progress
        _updateTask(taskId, TransferStatus.inProgress, status.progress);

        if (status.isCompleted) {
          _updateTask(taskId, TransferStatus.completed, 1.0);
          return true;
        } else if (status.isFailed) {
          _updateTask(taskId, TransferStatus.failed, status.progress,
              errorMessage: status.error ?? 'Transfer failed');
          return false;
        }
      }

      // Timeout after max attempts
      _updateTask(taskId, TransferStatus.failed, 0.0,
          errorMessage: 'Transfer timed out');
      return false;
    } catch (e, s) {
      AppLogger.error('Fetch task error', error: e, stackTrace: s);
      _updateTask(taskId, TransferStatus.failed, 0.0,
          errorMessage: e.toString());
      return false;
    }
  }

  // ---------------- INTERNAL ----------------
  void _updateTask(
    String id,
    TransferStatus status,
    double progress, {
    String? errorMessage,
  }) {
    final i = _tasks.indexWhere((t) => t.id == id);
    if (i == -1) return;

    _tasks[i] = _tasks[i].copyWith(
      status: status,
      progress: progress,
      errorMessage: errorMessage,
      completedAt: (status == TransferStatus.completed ||
              status == TransferStatus.failed)
          ? DateTime.now()
          : null,
    );
    notifyListeners();
    _saveHistory();
  }

  void clearCompleted() {
    _tasks.removeWhere((t) =>
        t.status == TransferStatus.completed ||
        t.status == TransferStatus.failed ||
        t.status == TransferStatus.cancelled);
    notifyListeners();
    _saveHistory();
  }

  void clearAll() {
    _tasks.clear();
    notifyListeners();
    _saveHistory();
  }
}
