import 'package:lanfxplorer/data/models/machine.dart';
import 'package:lanfxplorer/data/services/api_service.dart';
import 'package:flutter/material.dart';

class SessionProvider extends ChangeNotifier {
  Machine? _currentMachine;
  Machine? _destinationMachine;
  String? _connectionId;
  DateTime? _connectedAt;

  Machine? get currentMachine => _currentMachine;
  Machine? get destinationMachine => _destinationMachine;
  String? get connectionId => _connectionId;
  DateTime? get connectedAt => _connectedAt;
  bool get isActive => _connectionId != null && _destinationMachine != null;

  void setCurrentMachine(Machine machine) {
    _currentMachine = machine;
    notifyListeners();
  }

  void startSession(Machine destination) {
    _destinationMachine = destination;
    _connectionId = '${DateTime.now().millisecondsSinceEpoch}';
    _connectedAt = DateTime.now();
    notifyListeners();
  }

  void endSession() {
    _destinationMachine = null;
    _connectionId = null;
    _connectedAt = null;
    notifyListeners();
  }

  Future<bool> reconnect(ApiService api) async {
    if (_destinationMachine == null) return false;

    final ok = await api.connect();
    if (!ok) return false;

    _connectionId = '${DateTime.now().millisecondsSinceEpoch}';
    _connectedAt = DateTime.now();
    notifyListeners();
    return true;
  }
}
