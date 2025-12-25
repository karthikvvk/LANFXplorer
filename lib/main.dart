import 'package:lanfxplorer/data/services/api_service.dart';
import 'package:lanfxplorer/presentation/providers/env_provider.dart';
import 'package:lanfxplorer/presentation/providers/file_system_provider.dart';
import 'package:lanfxplorer/presentation/providers/network_provider.dart';
import 'package:lanfxplorer/presentation/providers/session_provider.dart';
import 'package:lanfxplorer/presentation/providers/theme_provider.dart';
import 'package:lanfxplorer/presentation/providers/transfer_provider.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'theme.dart';
import 'nav.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    final apiService = ApiService();

    return MultiProvider(
      providers: [
        Provider<ApiService>.value(value: apiService),

        ChangeNotifierProvider(create: (_) => EnvProvider(apiService)),
        ChangeNotifierProvider(create: (_) => SessionProvider()),
        ChangeNotifierProvider(create: (_) => ThemeProvider()),
        ChangeNotifierProvider(create: (_) => NetworkProvider(apiService)),
        ChangeNotifierProvider(
          create: (_) => FileSystemProvider(apiService: apiService),
        ),

        // ✅ CORRECT TransferProvider wiring
        ChangeNotifierProvider<TransferProvider>(
          create: (context) => TransferProvider(
            apiService,
          ),
        ),
      ],
      child: Consumer<ThemeProvider>(
        builder: (context, theme, _) => MaterialApp.router(
          title: 'P2P File Share',
          debugShowCheckedModeBanner: false,
          theme: lightTheme,
          darkTheme: darkTheme,
          themeMode: theme.themeMode,
          routerConfig: AppRouter.router,
        ),
      ),
    );
  }
}
