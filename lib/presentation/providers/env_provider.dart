import 'package:files/data/services/env_writer.dart';
import 'package:flutter/material.dart';
import '../../data/models/app_env.dart';
import '../../data/services/api_service.dart';
import '../../data/services/env_loader.dart';

class EnvProvider extends ChangeNotifier {
  final ApiService _apiService;
  AppEnv? _env;

  EnvProvider(this._apiService);

  AppEnv? get env => _env;
  bool get isLoaded => _env != null;

  Future<void> load() async {
    if (_env != null) return;

    _env = await EnvLoader.load();
    notifyListeners();
  }

  Future<void> updateDestHost(String host) async {
    if (_env == null) return;
    _env = _env!.copyWith(destHost: host);
    notifyListeners();

    await EnvWriter.setValue('DEST_HOST', host);
    // final env = await EnvLoader.load();
  }
}
