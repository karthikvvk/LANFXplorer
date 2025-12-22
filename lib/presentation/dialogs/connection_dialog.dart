import 'package:files/data/models/machine.dart';
import 'package:files/data/services/api_service.dart';
import 'package:files/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

/// Dialog shown when user taps a machine card to initiate connection.
/// Displays machine info and prompts for password authentication.
class ConnectionDialog extends StatefulWidget {
  final Machine machine;
  final ApiService apiService;

  const ConnectionDialog({
    super.key,
    required this.machine,
    required this.apiService,
  });

  @override
  State<ConnectionDialog> createState() => _ConnectionDialogState();
}

class _ConnectionDialogState extends State<ConnectionDialog> {
  final _passwordController = TextEditingController();
  final _formKey = GlobalKey<FormState>();

  bool _isConnecting = false;
  bool _obscurePassword = true;
  String? _errorMessage;
  bool _showSuccess = false;

  @override
  void dispose() {
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _handleConnect() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _isConnecting = true;
      _errorMessage = null;
    });

    try {
      final result = await widget.apiService.initiateHandshake(
        destHost: widget.machine.ipAddress,
        password: _passwordController.text,
      );

      if (result.success) {
        setState(() {
          _showSuccess = true;
          _isConnecting = false;
        });

        // Wait a moment to show success animation
        await Future.delayed(const Duration(milliseconds: 800));

        if (mounted) {
          // Close dialog and return success
          Navigator.of(context).pop(true);
        }
      } else {
        setState(() {
          _isConnecting = false;
          _errorMessage = result.error ?? 'Authentication failed';
        });
      }
    } catch (e) {
      setState(() {
        _isConnecting = false;
        _errorMessage = 'Connection error: $e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    if (_showSuccess) {
      return _buildSuccessDialog(colorScheme);
    }

    return Dialog(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadius.lg),
      ),
      child: Container(
        constraints: const BoxConstraints(maxWidth: 400),
        padding: AppSpacing.paddingLg,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Header
            Row(
              children: [
                Icon(
                  Icons.lan_outlined,
                  color: colorScheme.primary,
                  size: 28,
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Text(
                    'Connect to Device',
                    style: context.textStyles.titleLarge?.semiBold,
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.close),
                  onPressed: _isConnecting
                      ? null
                      : () => Navigator.of(context).pop(false),
                ),
              ],
            ),

            const SizedBox(height: AppSpacing.lg),

            // Machine Info Card
            Container(
              padding: AppSpacing.paddingMd,
              decoration: BoxDecoration(
                color: colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(AppRadius.md),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildInfoRow(
                    context,
                    Icons.person_outline,
                    'Username',
                    widget.machine.username,
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  _buildInfoRow(
                    context,
                    Icons.router_outlined,
                    'IP Address',
                    widget.machine.ipAddress,
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  _buildInfoRow(
                    context,
                    Icons.computer_outlined,
                    'OS',
                    widget.machine.os.toUpperCase(),
                  ),
                ],
              ),
            ),

            const SizedBox(height: AppSpacing.lg),

            // Password Form
            Form(
              key: _formKey,
              child: TextFormField(
                controller: _passwordController,
                obscureText: _obscurePassword,
                enabled: !_isConnecting,
                autofocus: true,
                decoration: InputDecoration(
                  labelText: 'Password',
                  hintText: 'Enter peer password',
                  prefixIcon: const Icon(Icons.lock_outline),
                  suffixIcon: IconButton(
                    icon: Icon(
                      _obscurePassword
                          ? Icons.visibility_outlined
                          : Icons.visibility_off_outlined,
                    ),
                    onPressed: () {
                      setState(() {
                        _obscurePassword = !_obscurePassword;
                      });
                    },
                  ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(AppRadius.md),
                  ),
                ),
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return 'Password is required';
                  }
                  return null;
                },
                onFieldSubmitted: (_) => _handleConnect(),
              ),
            ),

            // Error Message
            if (_errorMessage != null) ...[
              const SizedBox(height: AppSpacing.md),
              Container(
                padding: AppSpacing.paddingMd,
                decoration: BoxDecoration(
                  color: colorScheme.errorContainer,
                  borderRadius: BorderRadius.circular(AppRadius.sm),
                ),
                child: Row(
                  children: [
                    Icon(
                      Icons.error_outline,
                      color: colorScheme.onErrorContainer,
                      size: 20,
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Text(
                        _errorMessage!,
                        style: context.textStyles.bodySmall?.copyWith(
                          color: colorScheme.onErrorContainer,
                        ),
                      ),
                    ),
                  ],
                ),
              ).animate().fadeIn(duration: 300.ms).slideY(begin: -0.2, end: 0),
            ],

            const SizedBox(height: AppSpacing.lg),

            // Action Buttons
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  onPressed: _isConnecting
                      ? null
                      : () => Navigator.of(context).pop(false),
                  child: const Text('Cancel'),
                ),
                const SizedBox(width: AppSpacing.sm),
                FilledButton.icon(
                  onPressed: _isConnecting ? null : _handleConnect,
                  icon: _isConnecting
                      ? SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: colorScheme.onPrimary,
                          ),
                        )
                      : const Icon(Icons.login),
                  label: Text(_isConnecting ? 'Connecting...' : 'Connect'),
                ),
              ],
            ),
          ],
        ),
      ),
    ).animate().fadeIn(duration: 200.ms).scale(begin: const Offset(0.9, 0.9));
  }

  Widget _buildInfoRow(
    BuildContext context,
    IconData icon,
    String label,
    String value,
  ) {
    final colorScheme = Theme.of(context).colorScheme;
    return Row(
      children: [
        Icon(icon, size: 16, color: colorScheme.onSurfaceVariant),
        const SizedBox(width: AppSpacing.sm),
        Text(
          '$label: ',
          style: context.textStyles.bodySmall?.copyWith(
            color: colorScheme.onSurfaceVariant,
          ),
        ),
        Text(
          value,
          style: context.textStyles.bodySmall?.semiBold,
        ),
      ],
    );
  }

  Widget _buildSuccessDialog(ColorScheme colorScheme) {
    return Dialog(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadius.lg),
      ),
      child: Container(
        constraints: const BoxConstraints(maxWidth: 300),
        padding: AppSpacing.paddingXl,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.green.withValues(alpha: 0.1),
                shape: BoxShape.circle,
              ),
              child: Icon(
                Icons.check_circle_outline,
                size: 48,
                color: Colors.green.shade600,
              ),
            )
                .animate()
                .scale(duration: 400.ms, curve: Curves.elasticOut)
                .fadeIn(),
            const SizedBox(height: AppSpacing.lg),
            Text(
              'Connected!',
              style: context.textStyles.titleLarge?.semiBold,
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              'Authentication successful',
              style: context.textStyles.bodyMedium?.copyWith(
                color: colorScheme.onSurfaceVariant,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    ).animate().fadeIn(duration: 200.ms);
  }
}

/// Result of handshake operation
class HandshakeResult {
  final bool success;
  final String? error;

  HandshakeResult({required this.success, this.error});

  factory HandshakeResult.fromJson(Map<String, dynamic> json) {
    return HandshakeResult(
      success: json['success'] ?? false,
      error: json['error'],
    );
  }
}
