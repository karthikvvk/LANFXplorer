import 'package:flutter/foundation.dart';

class AppLogger {
  static void log(String message, {String? tag}) {
    if (kDebugMode) {
      debugPrint('[${tag ?? 'APP'}] $message');
    }
  }
  
  static void error(String message, {Object? error, StackTrace? stackTrace}) {
    if (kDebugMode) {
      debugPrint('[ERROR] $message');
      if (error != null) debugPrint('Error: $error');
      if (stackTrace != null) debugPrint('Stack trace: $stackTrace');
    }
  }
  
  static void info(String message) => log(message, tag: 'INFO');
  static void warning(String message) => log(message, tag: 'WARNING');
  static void network(String message) => log(message, tag: 'NETWORK');
  static void transfer(String message) => log(message, tag: 'TRANSFER');
}