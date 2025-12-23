import 'package:files/core/constants/enums.dart';
import 'package:files/core/utils/logger.dart';
import 'package:files/data/models/file_item.dart';
import 'package:files/data/models/transfer_task.dart';
import 'package:files/data/services/api_service.dart';
import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

class TransferProvider extends ChangeNotifier {
  final ApiService _apiService;

  final List<TransferTask> _tasks = [];
  final _uuid = const Uuid();

  TransferProvider(
    this._apiService,
  );

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
  Future<bool> sendFiles(String destinationId, List<FileItem> files) async {
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
      final result = await _apiService.sendFiles(destinationId, paths);

      if (result == null) {
        _updateTask(taskId, TransferStatus.failed, 0.0,
            errorMessage: 'Failed to initiate transfer');
        return false;
      }

      final backendTaskId = result.taskId;

      // Poll for progress
      bool isComplete = false;
      while (!isComplete) {
        await Future.delayed(const Duration(milliseconds: 500));

        final status = await _apiService.getTransferStatus(backendTaskId);
        if (status == null) {
          // Polling failed, but transfer might still be running
          continue;
        }

        // Update local task with progress
        _updateTask(taskId, TransferStatus.inProgress, status.progress);

        if (status.isCompleted) {
          _updateTask(taskId, TransferStatus.completed, 1.0);
          isComplete = true;
          return true;
        } else if (status.isFailed) {
          _updateTask(taskId, TransferStatus.failed, status.progress,
              errorMessage: status.error ?? 'Transfer failed');
          isComplete = true;
          return false;
        }
      }

      return false;
    } catch (e, s) {
      AppLogger.error('Send task error', error: e, stackTrace: s);
      _updateTask(taskId, TransferStatus.failed, 0.0,
          errorMessage: e.toString());
      return false;
    }
  }

  // ---------------- RECEIVE ----------------
  Future<bool> fetchFiles(String sourceId, List<FileItem> files) async {
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
      final ok = await _apiService.fetchFiles(sourceId, paths);

      _updateTask(
        taskId,
        ok ? TransferStatus.completed : TransferStatus.failed,
        ok ? 1.0 : 0.0,
        errorMessage: ok ? null : 'Failed to fetch files',
      );

      return ok;
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
  }

  void clearCompleted() {
    _tasks.removeWhere((t) =>
        t.status == TransferStatus.completed ||
        t.status == TransferStatus.failed ||
        t.status == TransferStatus.cancelled);
    notifyListeners();
  }

  void clearAll() {
    _tasks.clear();
    notifyListeners();
  }
}
