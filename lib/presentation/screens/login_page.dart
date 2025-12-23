import 'package:files/presentation/providers/env_provider.dart';
import 'package:files/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:file_picker/file_picker.dart';
import 'package:provider/provider.dart';
import 'dart:io';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _formKey = GlobalKey<FormState>();
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  final _defaultDirController = TextEditingController();

  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    // Set default directory to Downloads
    _defaultDirController.text = _getDefaultDownloadsPath();
  }

  String _getDefaultDownloadsPath() {
    if (Platform.isLinux || Platform.isMacOS) {
      final home = Platform.environment['HOME'] ?? '/home';
      return '$home/Downloads';
    } else if (Platform.isWindows) {
      final userProfile = Platform.environment['USERPROFILE'] ?? 'C:\\Users';
      return '$userProfile\\Downloads';
    }
    return 'Downloads';
  }

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    _defaultDirController.dispose();
    super.dispose();
  }

  Future<void> _selectDirectory() async {
    final result = await FilePicker.platform.getDirectoryPath();
    if (result != null) {
      setState(() {
        _defaultDirController.text = result;
      });
    }
  }

  void _createProfile() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isLoading = true);

    try {
      // Write to .env file
      final envFile = File('.env');
      String envContent = '';
      if (await envFile.exists()) {
        envContent = await envFile.readAsString();
      }

      // Update or add PASSWORD and OUTDIR
      final password = _passwordController.text;
      final outdir = _defaultDirController.text;
      final username = _usernameController.text;

      // Parse existing env and update
      final lines = envContent.split('\n');
      final newLines = <String>[];
      bool foundPassword = false;
      bool foundOutdir = false;
      bool foundUser = false;

      for (final line in lines) {
        if (line.startsWith('PASSWORD=')) {
          newLines.add('PASSWORD=$password');
          foundPassword = true;
        } else if (line.startsWith('OUTDIR=')) {
          newLines.add('OUTDIR=$outdir');
          foundOutdir = true;
        } else if (line.startsWith('USER=')) {
          newLines.add('USER=$username');
          foundUser = true;
        } else {
          newLines.add(line);
        }
      }

      if (!foundPassword) newLines.add('PASSWORD=$password');
      if (!foundOutdir) newLines.add('OUTDIR=$outdir');
      if (!foundUser) newLines.add('USER=$username');

      await envFile.writeAsString(newLines.join('\n'));

      if (mounted) {
        // Reload environment so username persists throughout the app
        await context.read<EnvProvider>().forceReload();
        context.go('/home');
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error creating profile: $e')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  void _useDefaultValues() {
    _usernameController.text = Platform.environment['USER'] ?? 'user';
    _passwordController.text = 'password';
    _confirmPasswordController.text = 'password';
    _defaultDirController.text = _getDefaultDownloadsPath();
    _createProfile();
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: AppSpacing.paddingXl,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 400),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // App Logo/Icon
                  Icon(
                    Icons.folder_shared,
                    size: 72,
                    color: colorScheme.primary,
                  )
                      .animate()
                      .fadeIn(duration: 500.ms)
                      .scale(begin: const Offset(0.5, 0.5)),

                  const SizedBox(height: AppSpacing.md),

                  // Title
                  Text(
                    'P2P File Share',
                    style: context.textStyles.headlineMedium?.semiBold,
                    textAlign: TextAlign.center,
                  ).animate().fadeIn(duration: 500.ms, delay: 100.ms),

                  Text(
                    'Create your profile to get started',
                    style: context.textStyles.bodyMedium
                        ?.withColor(colorScheme.onSurfaceVariant),
                    textAlign: TextAlign.center,
                  ).animate().fadeIn(duration: 500.ms, delay: 200.ms),

                  const SizedBox(height: AppSpacing.xxl),

                  // Username field
                  TextFormField(
                    controller: _usernameController,
                    decoration: InputDecoration(
                      labelText: 'Enter Username',
                      prefixIcon: const Icon(Icons.person_outline),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(AppRadius.md),
                      ),
                    ),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter a username';
                      }
                      return null;
                    },
                  )
                      .animate()
                      .fadeIn(duration: 400.ms, delay: 300.ms)
                      .slideX(begin: -0.1, end: 0),

                  const SizedBox(height: AppSpacing.md),

                  // Password field
                  TextFormField(
                    controller: _passwordController,
                    obscureText: _obscurePassword,
                    decoration: InputDecoration(
                      labelText: 'Enter Password',
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                        icon: Icon(_obscurePassword
                            ? Icons.visibility_off
                            : Icons.visibility),
                        onPressed: () => setState(
                            () => _obscurePassword = !_obscurePassword),
                      ),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(AppRadius.md),
                      ),
                    ),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter a password';
                      }
                      if (value.length < 4) {
                        return 'Password must be at least 4 characters';
                      }
                      return null;
                    },
                  )
                      .animate()
                      .fadeIn(duration: 400.ms, delay: 400.ms)
                      .slideX(begin: -0.1, end: 0),

                  const SizedBox(height: AppSpacing.md),

                  // Confirm Password field
                  TextFormField(
                    controller: _confirmPasswordController,
                    obscureText: _obscureConfirmPassword,
                    decoration: InputDecoration(
                      labelText: 'Confirm Password',
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                        icon: Icon(_obscureConfirmPassword
                            ? Icons.visibility_off
                            : Icons.visibility),
                        onPressed: () => setState(() =>
                            _obscureConfirmPassword = !_obscureConfirmPassword),
                      ),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(AppRadius.md),
                      ),
                    ),
                    validator: (value) {
                      if (value != _passwordController.text) {
                        return 'Passwords do not match';
                      }
                      return null;
                    },
                  )
                      .animate()
                      .fadeIn(duration: 400.ms, delay: 500.ms)
                      .slideX(begin: -0.1, end: 0),

                  const SizedBox(height: AppSpacing.md),

                  // Default Directory field
                  TextFormField(
                    controller: _defaultDirController,
                    readOnly: true,
                    decoration: InputDecoration(
                      labelText: 'Select Default Directory',
                      hintText: 'Downloads (default)',
                      prefixIcon: const Icon(Icons.folder_outlined),
                      suffixIcon: IconButton(
                        icon: const Icon(Icons.folder_open),
                        onPressed: _selectDirectory,
                        tooltip: 'Browse',
                      ),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(AppRadius.md),
                      ),
                    ),
                    onTap: _selectDirectory,
                  )
                      .animate()
                      .fadeIn(duration: 400.ms, delay: 600.ms)
                      .slideX(begin: -0.1, end: 0),

                  const SizedBox(height: AppSpacing.xl),

                  // Create Profile button
                  FilledButton(
                    onPressed: _isLoading ? null : _createProfile,
                    style: FilledButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(AppRadius.md),
                      ),
                    ),
                    child: _isLoading
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Create Profile'),
                  )
                      .animate()
                      .fadeIn(duration: 400.ms, delay: 700.ms)
                      .slideY(begin: 0.2, end: 0),

                  const SizedBox(height: AppSpacing.md),

                  // Use Default Values button (dull/secondary)
                  OutlinedButton(
                    onPressed: _isLoading ? null : _useDefaultValues,
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      foregroundColor: colorScheme.onSurfaceVariant,
                      side: BorderSide(
                          color: colorScheme.outline.withOpacity(0.5)),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(AppRadius.md),
                      ),
                    ),
                    child: const Text('Use Default Values'),
                  )
                      .animate()
                      .fadeIn(duration: 400.ms, delay: 800.ms)
                      .slideY(begin: 0.2, end: 0),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
