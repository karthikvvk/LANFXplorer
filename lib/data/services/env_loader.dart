import 'dart:io';

import '../models/app_env.dart';

class EnvLoader {
  static Future<AppEnv> load() async {
    final envFile = File('.env');

    if (!envFile.existsSync()) {
      throw Exception('.env file not found');
    }

    final lines = await envFile.readAsLines();

    final Map<String, String> env = {};

    for (final line in lines) {
      if (line.trim().isEmpty || line.startsWith('#')) continue;
      final idx = line.indexOf('=');
      if (idx == -1) continue;

      final key = line.substring(0, idx).trim();
      if (key.isEmpty) continue;
      var value = line.substring(idx + 1).trim();

      // strip quotes
      if (value.startsWith("'") && value.endsWith("'")) {
        value = value.substring(1, value.length - 1);
      }
      if (value.startsWith('"') && value.endsWith('"')) {
        value = value.substring(1, value.length - 1);
      }

      env[key] = value;
    }

    return AppEnv(
      host: env['HOST'] ?? '',
      port: int.tryParse(env['PORT'] ?? '') ?? 4433,
      user: env['USER'] ?? '',
      system: env['SYSTEM'] ?? '',
      interface: env['INTERFACE'] ?? '',
      subnet: env['SUBNET'] ?? '',
      gateway: env['GATEWAY'] ?? '',
      broadcast: env['BROADCAST'] ?? '',
      outDir: env['OUTDIR'] ?? '',
      srcDir: env['SRCDIR'] ?? '',
      certi: env['CERTI'] ?? '',
      key: env['KEY'] ?? '',
      pwd: env['PWD'] ?? '',
      cidr: env['CIDR'] ?? '',
      destHost: env['DEST_HOST'] ?? '',
      recivHost: env['RECIVHOST'] ?? '0.0.0.0',
    );
  }

  /// Check if password is configured.
  ///
  /// NOTE: As of the security refactor, passwords are now stored securely in
  /// the OS keyring (via config_manager.py), NOT in the .env file.
  /// This method now always returns true since password setup is handled
  /// by the Python backend's config_manager.
  ///
  /// DEPRECATED: Do not rely on this method for password detection.
  /// Use the /handshake endpoint to verify authentication capability.
  static Future<bool> hasPassword() async {
    // Passwords are now stored in OS keyring, not .env file
    // The config_manager.py handles secure password storage
    // Return true to indicate the backend should be consulted for password auth
    return true;
  }
}
