import 'dart:io';

class EnvWriter {
  static Future<void> setValue(String key, String value) async {
    final file = File('.env');

    if (!file.existsSync()) {
      throw Exception('.env file not found');
    }

    final lines = await file.readAsLines();
    bool updated = false;

    final newLines = lines.map((line) {
      final trimmed = line.trim();

      if (trimmed.isEmpty || trimmed.startsWith('#')) {
        return line;
      }

      final idx = line.indexOf('=');
      if (idx == -1) {
        return line;
      }

      final k = line.substring(0, idx).trim();
      if (k != key) {
        return line;
      }

      updated = true;
      return "$key='$value'";
    }).toList();

    if (!updated) {
      newLines.add("$key='$value'");
    }

    await file.writeAsString(
      newLines.join('\n'),
      mode: FileMode.write,
      flush: true,
    );
  }
}
