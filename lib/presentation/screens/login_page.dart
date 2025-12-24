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
  bool _isCheckingCredentials = true;
  String? _directoryError; // Error message when invalid directory selected

  @override
  void initState() {
    super.initState();
    // Set default directory to Downloads
    _defaultDirController.text = _getDefaultDownloadsPath();

    // Check if already logged in and redirect to home
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _checkExistingCredentials();
    });
  }

  Future<void> _checkExistingCredentials() async {
    final envProvider = context.read<EnvProvider>();
    await envProvider.load();

    if (envProvider.hasCredentials && mounted) {
      // User has already logged in before, go directly to home
      context.go('/home');
    } else {
      setState(() => _isCheckingCredentials = false);
    }
  }

  /// Get the allowed root directory - only paths within this are allowed
  String _getAllowedRootPath() {
    if (Platform.isLinux || Platform.isMacOS) {
      final home = Platform.environment['HOME'] ?? '/home';
      return '$home/Lanfxplorer';
    } else if (Platform.isWindows) {
      final userProfile = Platform.environment['USERPROFILE'] ?? 'C:\\Users';
      return '$userProfile\\Lanfxplorer';
    }
    return 'Lanfxplorer';
  }

  /// Check if a path is within the allowed Lanfxplorer directory
  bool _isPathAllowed(String path) {
    final allowedRoot = _getAllowedRootPath();
    // Normalize paths for comparison
    final normalizedPath = path.replaceAll('\\', '/');
    final normalizedRoot = allowedRoot.replaceAll('\\', '/');

    // Path must start with the allowed root (be within Lanfxplorer folder)
    return normalizedPath == normalizedRoot ||
        normalizedPath.startsWith('$normalizedRoot/');
  }

  String _getDefaultDownloadsPath() {
    // Default to Lanfxplorer folder
    return _getAllowedRootPath();
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
      // Validate the selected path is within allowed root
      if (_isPathAllowed(result)) {
        setState(() {
          _defaultDirController.text = result;
          _directoryError = null; // Clear any previous error
        });
      } else {
        final allowedRoot = _getAllowedRootPath();
        setState(() {
          _directoryError =
              'Access denied! You can only select directories within:\n$allowedRoot\n\nPlease create this folder if it doesn\'t exist.';
        });
        // Show snackbar as well for visibility
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                  'Invalid directory! Only paths within $allowedRoot are allowed.'),
              backgroundColor: Theme.of(context).colorScheme.error,
              duration: const Duration(seconds: 4),
            ),
          );
        }
      }
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
    _directoryError = null; // Default path is always valid
    _createProfile();
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    // Show loading while checking for existing credentials
    if (_isCheckingCredentials) {
      return Scaffold(
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.folder_shared, size: 72, color: colorScheme.primary),
              const SizedBox(height: AppSpacing.md),
              const CircularProgressIndicator(),
            ],
          ),
        ),
      );
    }

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
                      hintText: 'Lanfxplorer folder',
                      prefixIcon: const Icon(Icons.folder_outlined),
                      suffixIcon: IconButton(
                        icon: const Icon(Icons.folder_open),
                        onPressed: _selectDirectory,
                        tooltip: 'Browse',
                      ),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(AppRadius.md),
                      ),
                      // Show error border if directory is invalid
                      errorText: _directoryError != null ? null : null,
                      enabledBorder: _directoryError != null
                          ? OutlineInputBorder(
                              borderRadius: BorderRadius.circular(AppRadius.md),
                              borderSide: BorderSide(
                                  color: Theme.of(context).colorScheme.error,
                                  width: 2),
                            )
                          : null,
                    ),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please select a directory';
                      }
                      if (!_isPathAllowed(value)) {
                        return 'Directory must be within Lanfxplorer folder';
                      }
                      return null;
                    },
                    onTap: _selectDirectory,
                  )
                      .animate()
                      .fadeIn(duration: 400.ms, delay: 600.ms)
                      .slideX(begin: -0.1, end: 0),

                  // Error message for invalid directory
                  if (_directoryError != null)
                    Padding(
                      padding: const EdgeInsets.only(top: AppSpacing.sm),
                      child: Container(
                        padding: const EdgeInsets.all(AppSpacing.md),
                        decoration: BoxDecoration(
                          color: Theme.of(context).colorScheme.errorContainer,
                          borderRadius: BorderRadius.circular(AppRadius.sm),
                          border: Border.all(
                            color: Theme.of(context).colorScheme.error,
                            width: 1,
                          ),
                        ),
                        child: Row(
                          children: [
                            Icon(
                              Icons.warning_amber_rounded,
                              color: Theme.of(context).colorScheme.error,
                            ),
                            const SizedBox(width: AppSpacing.sm),
                            Expanded(
                              child: Text(
                                _directoryError!,
                                style: TextStyle(
                                  color: Theme.of(context)
                                      .colorScheme
                                      .onErrorContainer,
                                  fontSize: 13,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ).animate().fadeIn(duration: 200.ms).shake(),

                  const SizedBox(height: AppSpacing.xl),

                  // Create Profile button - disabled if directory is invalid
                  FilledButton(
                    onPressed: (_isLoading || _directoryError != null)
                        ? null
                        : _createProfile,
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
