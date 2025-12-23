import 'dart:convert';
import 'package:files/core/constants/api_endpoints.dart';
import 'package:files/core/utils/logger.dart';
import 'package:files/data/models/file_item.dart';
import 'package:files/data/models/machine.dart';
import 'package:http/http.dart' as http;

class ApiService {
  final http.Client _client;

  ApiService({http.Client? client}) : _client = client ?? http.Client();

  Future<List<Machine>> scanNetwork() async {
    try {
      AppLogger.network('Scanning network...');

      final response = await _client.get(
        Uri.parse('${ApiEndpoints.baseUrl}${ApiEndpoints.scan}'),
        headers: {'Accept': 'application/json'},
      ).timeout(const Duration(seconds: 10000));

      if (response.statusCode != 200) {
        AppLogger.error('Scan failed with status: ${response.statusCode}');
        return [];
      }

      final List<dynamic> rawList = jsonDecode(response.body);

      final List<Machine> machines = [];

      for (final item in rawList) {
        if (item is Map<String, dynamic>) {
          machines.add(Machine.fromJson(item));
        }
      }

      AppLogger.network('Found ${machines.length} machines');
      return machines;
    } catch (e, stack) {
      AppLogger.error(
        'Network scan error',
        error: e,
        stackTrace: stack,
      );
      return [];
    }
  }

  Future<bool> connect() async {
    try {
      AppLogger.network('Checking server health');

      final response = await _client
          .get(
            Uri.parse('${ApiEndpoints.baseUrl}${ApiEndpoints.connect}'),
          )
          .timeout(const Duration(seconds: 5));

      return response.statusCode == 200;
    } catch (e, stack) {
      AppLogger.error('Health check failed', error: e, stackTrace: stack);
      return false;
    }
  }

  Future<List<FileItem>> getFiles(String path, {String? remoteHost}) async {
    final Map<String, dynamic> body = {'path': path};
    if (remoteHost != null) {
      body['remote_host'] = remoteHost;
    }
    AppLogger.info('ApiService: Fetching files with body: $body');
    if (remoteHost == null) {
      AppLogger.warning(
          'ApiService: fetchFiles called with null remoteHost. This will fetch LOCAL files if not backend-handled.');
    }

    final response = await _client.post(
      Uri.parse('${ApiEndpoints.baseUrl}${ApiEndpoints.listDir}'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );

    if (response.statusCode != 200) return [];

    final data = jsonDecode(response.body);

    if (data['type'] != 'directory') return [];

    return (data['files'] as List)
        .map((f) => FileItem.fromJson({
              'name': f['name'],
              'path': f['path'],
              'is_directory': f['is_directory'],
              'size': f['size'],
              'modified': f['mtime'],
            }))
        .toList();
  }

  /// Initiates a file send and returns the task ID for progress tracking.
  /// Returns null if the request failed.
  /// [destDir] is the destination directory on the remote machine where files should be saved.
  Future<SendResult?> sendFiles(String remoteHost, List<String> filePaths,
      {String? destDir}) async {
    try {
      AppLogger.transfer(
          'Sending ${ApiEndpoints.baseUrl}${ApiEndpoints.transferSend} files to $remoteHost at destDir=$destDir');
      final Map<String, dynamic> body = {
        'remote_host': remoteHost,
        'files': filePaths,
      };
      if (destDir != null && destDir.isNotEmpty) {
        body['dest_dir'] = destDir;
      }
      final response = await _client
          .post(
            Uri.parse('${ApiEndpoints.baseUrl}${ApiEndpoints.transferSend}'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 60));

      if (response.statusCode == 202 || response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return SendResult(
          taskId: data['task_id'] ?? '',
          status: data['status'] ?? 'unknown',
          files: List<String>.from(data['files'] ?? filePaths),
        );
      }
      AppLogger.error('Send files failed: ${response.statusCode}');
      return null;
    } catch (e, stack) {
      AppLogger.error('Send files error', error: e, stackTrace: stack);
      return null;
    }
  }

  /// Poll the status of a transfer task.
  Future<TransferStatusResult?> getTransferStatus(String taskId) async {
    try {
      final response = await _client.get(
        Uri.parse('${ApiEndpoints.baseUrl}/transfer_status/$taskId'),
        headers: {'Accept': 'application/json'},
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return TransferStatusResult.fromJson(data);
      }
      return null;
    } catch (e) {
      AppLogger.error('Get transfer status error: $e');
      return null;
    }
  }

  Future<bool> fetchFiles(String remoteHost, List<String> filePaths) async {
    try {
      AppLogger.transfer('Fetching $filePaths files from $remoteHost');
      final response = await _client
          .post(
            Uri.parse('${ApiEndpoints.baseUrl}${ApiEndpoints.transferFetch}'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'remote_host': remoteHost, 'files': filePaths}),
          )
          .timeout(const Duration(seconds: 60));

      return response.statusCode == 200;
    } catch (e, stack) {
      AppLogger.error('Fetch files error', error: e, stackTrace: stack);
      return false;
    }
  }

  Future<HandshakeResult> initiateHandshake({
    required String destHost,
    required String password,
  }) async {
    try {
      AppLogger.network('Initiating handshake with $destHost');

      final response = await _client
          .post(
            Uri.parse('${ApiEndpoints.baseUrl}/handshake'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'dest_host': destHost,
              'password': password,
            }),
          )
          .timeout(const Duration(seconds: 100));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return HandshakeResult.fromJson(data);
      } else if (response.statusCode == 401) {
        // Authentication failed
        final data = jsonDecode(response.body);
        return HandshakeResult(
          success: false,
          error: data['error'] ?? 'Invalid password',
        );
      } else {
        return HandshakeResult(
          success: false,
          error: 'Connection failed (${response.statusCode})',
        );
      }
    } catch (e, stack) {
      AppLogger.error('Handshake error', error: e, stackTrace: stack);
      return HandshakeResult(
        success: false,
        error: 'Connection error: ${e.toString()}',
      );
    }
  }

  void dispose() {
    _client.close();
  }
}

/// Result of handshake operation
class HandshakeResult {
  final bool success;
  final String? error;

  HandshakeResult({required this.success, this.error});

  factory HandshakeResult.fromJson(Map<String, dynamic> json) {
    return HandshakeResult(
      success: json['success'] ?? false,
      error: json['error'],
    );
  }
}

/// Result of initiating a file send operation
class SendResult {
  final String taskId;
  final String status;
  final List<String> files;

  SendResult({
    required this.taskId,
    required this.status,
    required this.files,
  });
}

/// Result of polling transfer status
class TransferStatusResult {
  final String status; // 'in_progress', 'completed', 'failed'
  final double progress; // 0.0 to 1.0
  final int totalSize;
  final int transferred;
  final List<String> files;
  final String? currentFile;
  final String? error;

  TransferStatusResult({
    required this.status,
    required this.progress,
    required this.totalSize,
    required this.transferred,
    required this.files,
    this.currentFile,
    this.error,
  });

  factory TransferStatusResult.fromJson(Map<String, dynamic> json) {
    return TransferStatusResult(
      status: json['status'] ?? 'unknown',
      progress: (json['progress'] ?? 0).toDouble(),
      totalSize: json['total_size'] ?? 0,
      transferred: json['transferred'] ?? 0,
      files: List<String>.from(json['files'] ?? []),
      currentFile: json['current_file'],
      error: json['error'],
    );
  }

  bool get isCompleted => status == 'completed';
  bool get isFailed => status == 'failed';
  bool get isInProgress => status == 'in_progress';
}
