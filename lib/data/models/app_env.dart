import 'package:flutter/widgets.dart';

class AppEnv {
  final String host;
  final int port;
  final String user;
  final String system;
  final String interface;
  final String subnet;
  final String gateway;
  final String broadcast;
  final String outDir;
  final String srcDir;
  final String certi;
  final String key;

  AppEnv({
    required this.host,
    required this.port,
    required this.user,
    required this.system,
    required this.interface,
    required this.subnet,
    required this.gateway,
    required this.broadcast,
    required this.outDir,
    required this.srcDir,
    required this.certi,
    required this.key,
  });
}

class AppEnvScope extends InheritedWidget {
  final AppEnv env;

  const AppEnvScope({
    super.key,
    required this.env,
    required super.child,
  });

  static AppEnv of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AppEnvScope>();
    if (scope == null) {
      throw FlutterError('AppEnvScope not found in widget tree');
    }
    return scope.env;
  }

  @override
  bool updateShouldNotify(AppEnvScope oldWidget) => env != oldWidget.env;
}
