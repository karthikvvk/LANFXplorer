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
  final String pwd;
  final String cidr;
  final String destHost;
  final String recivHost;

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
    required this.pwd,
    required this.cidr,
    required this.destHost,
    required this.recivHost,
  });

  AppEnv copyWith({
    String? host,
    int? port,
    String? user,
    String? system,
    String? interface,
    String? subnet,
    String? gateway,
    String? broadcast,
    String? outDir,
    String? srcDir,
    String? certi,
    String? key,
    String? pwd,
    String? cidr,
    String? destHost,
    String? recivHost,
  }) {
    return AppEnv(
      host: host ?? this.host,
      port: port ?? this.port,
      user: user ?? this.user,
      system: system ?? this.system,
      interface: interface ?? this.interface,
      subnet: subnet ?? this.subnet,
      gateway: gateway ?? this.gateway,
      broadcast: broadcast ?? this.broadcast,
      outDir: outDir ?? this.outDir,
      srcDir: srcDir ?? this.srcDir,
      certi: certi ?? this.certi,
      key: key ?? this.key,
      pwd: pwd ?? this.pwd,
      cidr: cidr ?? this.cidr,
      destHost: destHost ?? this.destHost,
      recivHost: recivHost ?? this.recivHost,
    );
  }
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
