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
}
