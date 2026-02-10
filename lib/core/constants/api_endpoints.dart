class ApiEndpoints {
  static const String baseUrl = 'http://localhost:5000';

  static const String scan = '/listhost';
  static const String connect = '/health';
  static const String listDir = '/listdir';
  static const String transferSend = '/send_files';
  static const String transferFetch = '/receive_files';
  static const String reconnect = '/health';
  static const String defaultPath = '/default_path';
  static const String resetEnv = '/reset_environment';
}
