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

  Future<bool> updateEnv(String key, String value) async {
    try {
      AppLogger.network('Updating env: $key=$value');
      final response = await _client.post(
        Uri.parse('${ApiEndpoints.baseUrl}/update_env'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({key: value}),
      );

      return response.statusCode == 200;
    } catch (e) {
      AppLogger.error('Failed to update env', error: e);
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
      AppLogger.transfer('Sending ${filePaths.length} files to $remoteHost');
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

  void dispose() {
    _client.close();
  }
}
