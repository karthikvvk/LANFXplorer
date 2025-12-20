import 'package:flutter/material.dart';
import '../../data/models/app_env.dart';
import '../../data/services/env_loader.dart';

class EnvProvider extends ChangeNotifier {
  AppEnv? _env;

  AppEnv? get env => _env;
  bool get isLoaded => _env != null;

  Future<void> load() async {
    if (_env != null) return;

    _env = await EnvLoader.load();
    notifyListeners();
  }
}
