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

  Future<bool> sendFiles(String remoteHost, List<String> filePaths) async {
    try {
      AppLogger.transfer(
          'Sending ${'${ApiEndpoints.baseUrl}${ApiEndpoints.transferSend}'} files to $remoteHost');
      final response = await _client
          .post(
            Uri.parse('${ApiEndpoints.baseUrl}${ApiEndpoints.transferSend}'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'remote_host': remoteHost,
              'files': filePaths,
            }),
          )
          .timeout(const Duration(seconds: 30));

      return response.statusCode == 200;
    } catch (e, stack) {
      AppLogger.error('Send files error', error: e, stackTrace: stack);
      return false;
    }
  }

  Future<bool> fetchFiles(String remoteHost, List<String> filePaths) async {
    try {
      AppLogger.transfer('Fetching ${filePaths} files from $remoteHost');
      final response = await _client
          .post(
            Uri.parse('${ApiEndpoints.baseUrl}${ApiEndpoints.transferFetch}'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'remote_host': remoteHost, 'files': filePaths}),
          )
          .timeout(const Duration(seconds: 30));

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
