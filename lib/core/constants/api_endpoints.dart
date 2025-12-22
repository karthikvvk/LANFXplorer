class ApiEndpoints {
  static const String baseUrl = 'http://10.51.136.182:5000';

  static const String scan = '/listhost';
  static const String connect = '/health';
  static const String listDir = '/listdir'; // FIXED
  static const String transferSend = '/send_files';
  static const String transferFetch = '/receive_files';
  static const String reconnect = '/health';
}
