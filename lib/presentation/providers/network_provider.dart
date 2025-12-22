import 'package:files/core/utils/logger.dart';
import 'package:files/data/models/machine.dart';
import 'package:files/data/services/api_service.dart';
import 'package:flutter/foundation.dart';

class NetworkProvider extends ChangeNotifier {
  final ApiService _apiService;
  List<Machine> _availableMachines = [];
  bool _isScanning = false;

  NetworkProvider(this._apiService);

  List<Machine> get availableMachines => _availableMachines;
  bool get isScanning => _isScanning;
  ApiService get apiService => _apiService;

  Future<void> scanNetwork() async {
    _isScanning = true;
    notifyListeners();

    try {
      AppLogger.network('Starting network scan...');
      _availableMachines = await _apiService.scanNetwork();

      if (_availableMachines.isEmpty) {
        AppLogger.warning('No machines found, using mock data');
        // _availableMachines = _generateMockMachines();
      }
    } catch (e, stack) {
      AppLogger.error('Network scan failed, using mock data',
          error: e, stackTrace: stack);
      // _availableMachines = _generateMockMachines();
    }

    _isScanning = false;
    notifyListeners();
  }

  // List<Machine> _generateMockMachines() => [
  //   Machine(id: '1', username: 'PC-Office-01', ipAddress: '192.168.1.101'),
  //   Machine(id: '2', username: 'PC-Lab-02', ipAddress: '192.168.1.102'),
  //   Machine(id: '3', username: 'PC-Dev-03', ipAddress: '192.168.1.103'),
  //   Machine(id: '4', username: 'PC-Server-04', ipAddress: '192.168.1.104'),
  //   Machine(id: '5', username: 'PC-Guest-05', ipAddress: '192.168.1.105'),
  //   Machine(id: '6', username: 'PC-Mobile-06', ipAddress: '192.168.1.106'),
  // ];

  void clearMachines() {
    _availableMachines = [];
    notifyListeners();
  }
}
