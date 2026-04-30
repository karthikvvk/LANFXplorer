import 'dart:convert';
import 'package:lanfxplorer/core/constants/api_endpoints.dart';
import 'package:lanfxplorer/core/utils/logger.dart';
import 'package:lanfxplorer/data/models/file_item.dart';
import 'package:lanfxplorer/data/models/machine.dart';
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

  /// Get the default path (Lanfxplorer root) from a peer.
  /// If remoteHost is provided, fetches from that remote host,
  /// otherwise returns local default path.
  Future<String?> getDefaultPath({String? remoteHost}) async {
    try {
      AppLogger.network('Getting default path for ${remoteHost ?? "local"}');

      final Map<String, dynamic> body = {};
      if (remoteHost != null) {
        body['remote_host'] = remoteHost;
      }

      final response = await _client
          .post(
            Uri.parse('${ApiEndpoints.baseUrl}${ApiEndpoints.defaultPath}'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final defaultPath = data['default_path'] as String?;
        AppLogger.info('Got default path: $defaultPath');
        return defaultPath;
      }
      AppLogger.error('Failed to get default path: ${response.statusCode}');
      return null;
    } catch (e, stack) {
      AppLogger.error('Get default path error', error: e, stackTrace: stack);
      return null;
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

    AppLogger.info('ApiService: Response status=${response.statusCode}');

    if (response.statusCode != 200) {
      AppLogger.error(
          'ApiService: Failed with status ${response.statusCode}: ${response.body}');
      throw Exception('API returned ${response.statusCode}: ${response.body}');
    }

    final data = jsonDecode(response.body);
    AppLogger.info(
        'ApiService: Response type=${data['type']}, fileCount=${(data['files'] as List?)?.length ?? 0}');

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
      ).timeout(const Duration(seconds: 300));

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

  /// Initiates a file fetch (receive) and returns the remote task ID for progress tracking.
  /// This asks the remote host to send files to us.
  /// Returns null if the request failed.
  /// [destDir] is the local directory where files should be saved.
  Future<SendResult?> fetchFiles(String remoteHost, List<String> filePaths,
      {String? destDir}) async {
    try {
      AppLogger.transfer(
          'Fetching $filePaths files from $remoteHost to destDir=$destDir');
      final Map<String, dynamic> body = {
        'remote_host': remoteHost,
        'files': filePaths,
      };
      if (destDir != null && destDir.isNotEmpty) {
        body['dest_dir'] = destDir;
      }
      final response = await _client
          .post(
            Uri.parse('${ApiEndpoints.baseUrl}${ApiEndpoints.transferFetch}'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 60));

      if (response.statusCode == 200) {
        // The response contains the remote task info
        final data = jsonDecode(response.body);
        final remoteResponse = data['remote_response'] as Map<String, dynamic>?;
        if (remoteResponse != null) {
          return SendResult(
            taskId: remoteResponse['task_id'] ?? '',
            status: remoteResponse['status'] ?? 'unknown',
            files: List<String>.from(remoteResponse['files'] ?? filePaths),
          );
        }
      }
      AppLogger.error('Fetch files failed: ${response.statusCode}');
      return null;
    } catch (e, stack) {
      AppLogger.error('Fetch files error', error: e, stackTrace: stack);
      return null;
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

  /// Create a new empty file at the given path.
  /// If remoteHost is provided, the file is created on the remote machine.
  Future<bool> createFile(String path, {String? remoteHost}) async {
    try {
      final Map<String, dynamic> body = {'path': path};
      if (remoteHost != null) body['remote_host'] = remoteHost;

      final response = await _client
          .post(
            Uri.parse('${ApiEndpoints.baseUrl}${ApiEndpoints.createFile}'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 10));

      return response.statusCode == 200;
    } catch (e, stack) {
      AppLogger.error('Create file error', error: e, stackTrace: stack);
      return false;
    }
  }

  /// Create a new folder at the given path.
  Future<bool> createFolder(String path, {String? remoteHost}) async {
    try {
      final Map<String, dynamic> body = {'path': path};
      if (remoteHost != null) body['remote_host'] = remoteHost;

      final response = await _client
          .post(
            Uri.parse('${ApiEndpoints.baseUrl}${ApiEndpoints.createFolder}'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 10));

      return response.statusCode == 200;
    } catch (e, stack) {
      AppLogger.error('Create folder error', error: e, stackTrace: stack);
      return false;
    }
  }

  /// Delete a file or folder at the given path.
  Future<bool> deleteItem(String path, {String? remoteHost}) async {
    try {
      final Map<String, dynamic> body = {'path': path};
      if (remoteHost != null) body['remote_host'] = remoteHost;

      final response = await _client
          .post(
            Uri.parse('${ApiEndpoints.baseUrl}${ApiEndpoints.deleteItem}'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 10));

      return response.statusCode == 200;
    } catch (e, stack) {
      AppLogger.error('Delete item error', error: e, stackTrace: stack);
      return false;
    }
  }

  /// Reset environment: delete certificates and clear .env configs.
  /// The backend will restart the entire app after this call.
  Future<bool> resetEnvironment() async {
    try {
      AppLogger.info('Requesting environment reset...');
      final response = await _client.post(
        Uri.parse('${ApiEndpoints.baseUrl}${ApiEndpoints.resetEnv}'),
        headers: {'Content-Type': 'application/json'},
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        AppLogger.info('Environment reset successful');
        return true;
      }
      AppLogger.error('Reset failed: ${response.statusCode}');
      return false;
    } catch (e, stack) {
      AppLogger.error('Reset error', error: e, stackTrace: stack);
      return false;
    }
  }

  /// Trigger privileged firewall rule installation.
  /// Returns a map with {success, output, error}.
  Future<Map<String, dynamic>> fixFirewall() async {
    try {
      AppLogger.info('Requesting firewall fix...');
      final response = await _client.post(
        Uri.parse('${ApiEndpoints.baseUrl}${ApiEndpoints.fixFirewall}'),
        headers: {'Content-Type': 'application/json'},
      ).timeout(const Duration(seconds: 45));

      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return data;
    } catch (e, stack) {
      AppLogger.error('Fix firewall error', error: e, stackTrace: stack);
      return {'success': false, 'error': e.toString()};
    }
  }

  /// Check GitHub for a newer version. Returns null on network error.
  Future<Map<String, dynamic>?> checkUpdate() async {
    try {
      final response = await _client
          .get(Uri.parse('${ApiEndpoints.baseUrl}/update/check'))
          .timeout(const Duration(seconds: 15));
      if (response.statusCode == 200) return jsonDecode(response.body) as Map<String, dynamic>;
      return null;
    } catch (e) {
      AppLogger.error('checkUpdate error: $e');
      return null;
    }
  }

  /// Apply the latest update (download → extract → copy → pip upgrade).
  /// Long-running — may take 30–120 s depending on repo size and network.
  Future<Map<String, dynamic>> applyUpdate() async {
    try {
      final response = await _client
          .post(Uri.parse('${ApiEndpoints.baseUrl}/update/apply'))
          .timeout(const Duration(seconds: 180));
      return jsonDecode(response.body) as Map<String, dynamic>;
    } catch (e) {
      AppLogger.error('applyUpdate error: $e');
      return {'success': false, 'error': e.toString()};
    }
  }

  /// Store a new password in the OS keyring via the backend.
  Future<bool> setPassword(String password) async {
    try {
      final response = await _client
          .post(
            Uri.parse('${ApiEndpoints.baseUrl}/set_password'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'password': password}),
          )
          .timeout(const Duration(seconds: 10));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return data['success'] == true;
      }
      return false;
    } catch (e) {
      AppLogger.error('setPassword error: $e');
      return false;
    }
  }

  /// Get usable network interfaces (excludes lo).
  Future<List<Map<String, dynamic>>> getInterfaces() async {
    try {
      final response = await _client
          .get(Uri.parse('${ApiEndpoints.baseUrl}/interfaces'))
          .timeout(const Duration(seconds: 5));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return List<Map<String, dynamic>>.from(data['interfaces'] ?? []);
      }
      return [];
    } catch (e) {
      AppLogger.error('getInterfaces error: $e');
      return [];
    }
  }

  /// Switch the active network interface.
  Future<bool> setInterface(String interface) async {
    try {
      final response = await _client
          .post(
            Uri.parse('${ApiEndpoints.baseUrl}/set_interface'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'interface': interface}),
          )
          .timeout(const Duration(seconds: 5));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return data['success'] == true;
      }
      return false;
    } catch (e) {
      AppLogger.error('setInterface error: $e');
      return false;
    }
  }

  /// Update OUTDIR and/or SRCDIR on the backend.
  Future<bool> updateDirs({String? outDir, String? srcDir}) async {
    try {
      final body = <String, dynamic>{};
      if (outDir != null && outDir.isNotEmpty) body['outdir'] = outDir;
      if (srcDir != null && srcDir.isNotEmpty) body['srcdir'] = srcDir;
      final response = await _client
          .post(
            Uri.parse('${ApiEndpoints.baseUrl}/set_dirs'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 5));
      return response.statusCode == 200;
    } catch (e) {
      AppLogger.error('updateDirs error: $e');
      return false;
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
