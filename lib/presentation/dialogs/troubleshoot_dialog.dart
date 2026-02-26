import 'package:lanfxplorer/data/services/api_service.dart';
import 'package:lanfxplorer/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

/// Modal dialog with troubleshooting steps and a "FIX Firewall" button.
/// Shown when the user taps the Troubleshoot button in any header.
class TroubleshootDialog extends StatefulWidget {
  final ApiService apiService;

  const TroubleshootDialog({super.key, required this.apiService});

  @override
  State<TroubleshootDialog> createState() => _TroubleshootDialogState();
}

class _TroubleshootDialogState extends State<TroubleshootDialog> {
  bool _isFixing = false;
  String? _resultMessage;
  bool? _resultSuccess;

  Future<void> _fixFirewall() async {
    setState(() {
      _isFixing = true;
      _resultMessage = null;
      _resultSuccess = null;
    });

    final result = await widget.apiService.fixFirewall();

    if (!mounted) return;

    setState(() {
      _isFixing = false;
      _resultSuccess = result['success'] == true;
      if (_resultSuccess!) {
        _resultMessage = result['output']?.toString().isNotEmpty == true
            ? result['output']
            : 'Firewall rules applied successfully.';
      } else {
        _resultMessage = result['error'] ??
            result['output'] ??
            'Failed to apply firewall rules.';
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Dialog(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadius.lg),
      ),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520, maxHeight: 680),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // ── Title bar ──
            Container(
              padding: const EdgeInsets.all(AppSpacing.lg),
              decoration: BoxDecoration(
                color: colorScheme.primaryContainer,
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(AppRadius.lg),
                  topRight: Radius.circular(AppRadius.lg),
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    Icons.build_circle,
                    color: colorScheme.onPrimaryContainer,
                    size: 28,
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: Text(
                      'Troubleshoot',
                      style: context.textStyles.titleLarge?.copyWith(
                        color: colorScheme.onPrimaryContainer,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  IconButton(
                    icon: Icon(Icons.close,
                        color: colorScheme.onPrimaryContainer),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
            ),

            // ── Instruction steps ──
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.lg,
                  vertical: AppSpacing.md,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'If the app isn\'t connecting properly, try these steps in order:',
                      style: context.textStyles.bodyMedium?.withColor(
                        colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: AppSpacing.lg),

                    _StepTile(
                      step: 1,
                      icon: Icons.cached,
                      title: 'Clear Cache',
                      description:
                          'Close the application completely, delete any cached data '
                          '(browser cache, app data), and relaunch.',
                    ),
                    _StepTile(
                      step: 2,
                      icon: Icons.wifi_find,
                      title: 'Check Network Connection',
                      description:
                          'Verify your Wi-Fi or Ethernet cable is connected and active. '
                          'Try pinging your gateway or another device on the network.',
                    ),
                    _StepTile(
                      step: 3,
                      icon: Icons.lan,
                      title: 'Verify Correct Network',
                      description:
                          'Ensure both devices are on the same LAN / subnet. '
                          'Being on a different network (e.g. VPN, guest Wi-Fi) '
                          'can cause CA certificate mismatches and connection failures.',
                    ),
                    _StepTile(
                      step: 4,
                      icon: Icons.key,
                      title: 'Check Certificates & Keys',
                      description:
                          'Confirm the certs/ directory exists and contains valid '
                          'CA certificate, client certificate, and private key files. '
                          'If any are missing, re-run the setup.',
                    ),
                    _StepTile(
                      step: 5,
                      icon: Icons.shield,
                      title: 'Fix Firewall Rules',
                      description:
                          'Your system firewall may be blocking the required ports. '
                          'Click the button below to add the necessary allow-rules. '
                          'This requires administrator / sudo privileges.',
                    ),

                    const SizedBox(height: AppSpacing.lg),

                    // ── Result message ──
                    if (_resultMessage != null)
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(AppSpacing.md),
                        margin: const EdgeInsets.only(bottom: AppSpacing.md),
                        decoration: BoxDecoration(
                          color: _resultSuccess!
                              ? colorScheme.primaryContainer
                              : colorScheme.errorContainer,
                          borderRadius: BorderRadius.circular(AppRadius.sm),
                        ),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(
                              _resultSuccess!
                                  ? Icons.check_circle
                                  : Icons.error,
                              color: _resultSuccess!
                                  ? colorScheme.onPrimaryContainer
                                  : colorScheme.onErrorContainer,
                              size: 20,
                            ),
                            const SizedBox(width: AppSpacing.sm),
                            Expanded(
                              child: Text(
                                _resultMessage!,
                                style: context.textStyles.bodySmall?.copyWith(
                                  color: _resultSuccess!
                                      ? colorScheme.onPrimaryContainer
                                      : colorScheme.onErrorContainer,
                                ),
                                maxLines: 6,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                      ).animate().fadeIn(duration: 300.ms),
                  ],
                ),
              ),
            ),

            // ── Footer with FIX Firewall button ──
            Container(
              padding: const EdgeInsets.all(AppSpacing.lg),
              decoration: BoxDecoration(
                border: Border(
                  top: BorderSide(
                    color: colorScheme.outline.withValues(alpha: 0.2),
                  ),
                ),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      'Step 5 requires sudo privileges',
                      style: context.textStyles.bodySmall?.withColor(
                        colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  FilledButton.icon(
                    onPressed: _isFixing ? null : _fixFirewall,
                    icon: _isFixing
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Icon(Icons.shield, size: 18),
                    label: Text(_isFixing ? 'Fixing…' : 'FIX Firewall'),
                    style: FilledButton.styleFrom(
                      backgroundColor: colorScheme.primary,
                      foregroundColor: colorScheme.onPrimary,
                      padding: const EdgeInsets.symmetric(
                        horizontal: AppSpacing.lg,
                        vertical: AppSpacing.md,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A single numbered troubleshooting step.
class _StepTile extends StatelessWidget {
  final int step;
  final IconData icon;
  final String title;
  final String description;

  const _StepTile({
    required this.step,
    required this.icon,
    required this.title,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Step number badge
          Container(
            width: 28,
            height: 28,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: colorScheme.primary,
              shape: BoxShape.circle,
            ),
            child: Text(
              '$step',
              style: TextStyle(
                color: colorScheme.onPrimary,
                fontWeight: FontWeight.bold,
                fontSize: 13,
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(icon, size: 18, color: colorScheme.primary),
                    const SizedBox(width: AppSpacing.xs),
                    Text(
                      title,
                      style: context.textStyles.titleSmall?.semiBold,
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  description,
                  style: context.textStyles.bodySmall?.withColor(
                    colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    ).animate().fadeIn(duration: 200.ms, delay: (step * 60).ms).slideX(
          begin: 0.05,
          end: 0,
        );
  }
}
