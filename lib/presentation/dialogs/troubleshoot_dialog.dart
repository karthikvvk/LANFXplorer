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

                    const SizedBox(height: AppSpacing.md),

                    // ── Advanced Options (collapsible) ──
                    Theme(
                      data: Theme.of(context).copyWith(
                        dividerColor: Colors.transparent,
                      ),
                      child: ExpansionTile(
                        tilePadding: EdgeInsets.zero,
                        childrenPadding: const EdgeInsets.only(
                          bottom: AppSpacing.md,
                        ),
                        leading: Icon(
                          Icons.settings_suggest,
                          color: colorScheme.tertiary,
                          size: 22,
                        ),
                        title: Text(
                          'Advanced Options',
                          style: context.textStyles.titleSmall?.copyWith(
                            color: colorScheme.tertiary,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        children: [
                          // ── Diagnostic Checks ──
                          Padding(
                            padding: const EdgeInsets.only(
                              bottom: AppSpacing.sm,
                              top: AppSpacing.xs,
                            ),
                            child: Text(
                              'Network Diagnostic Checks',
                              style: context.textStyles.labelMedium?.copyWith(
                                color: colorScheme.onSurfaceVariant,
                                fontWeight: FontWeight.w600,
                                letterSpacing: 0.5,
                              ),
                            ),
                          ),
                          _AdvancedCheckTile(
                            icon: Icons.wifi_lock,
                            title: 'Check AP Isolation',
                            description:
                                'If devices can\'t see each other despite being on '
                                'the same Wi-Fi, AP (Access Point) isolation may be '
                                'enabled on your router. This blocks all '
                                'device-to-device traffic.',
                          ),
                          _AdvancedCheckTile(
                            icon: Icons.security,
                            title: 'DDoS Prevention Limits',
                            description:
                                'Some routers cap UDP & TCP connections per device. '
                                'LANFXplorer requires the limit set to >200 for '
                                'reliable peer discovery and file transfer.',
                          ),
                          _AdvancedCheckTile(
                            icon: Icons.router,
                            title: 'NAT Limitation',
                            description:
                                'Double NAT or strict NAT (common in VMs, '
                                'enterprise networks, and carrier-grade NAT) can '
                                'block peer-to-peer traffic even when both devices '
                                'have internet access.',
                          ),

                          const SizedBox(height: AppSpacing.md),
                          const Divider(height: 1),
                          const SizedBox(height: AppSpacing.md),

                          // ── Common Fixes ──
                          Padding(
                            padding: const EdgeInsets.only(
                              bottom: AppSpacing.sm,
                            ),
                            child: Text(
                              'Common Fixes',
                              style: context.textStyles.labelMedium?.copyWith(
                                color: colorScheme.onSurfaceVariant,
                                fontWeight: FontWeight.w600,
                                letterSpacing: 0.5,
                              ),
                            ),
                          ),
                          _FixTile(
                            number: 1,
                            text: 'Use a mobile hotspot — simplest test that '
                                'bypasses all router configuration issues.',
                          ),
                          _FixTile(
                            number: 2,
                            text: 'Disable AP-Isolation & UPnP in your router '
                                'admin panel (usually under Wireless / '
                                'Advanced settings).',
                          ),
                          _FixTile(
                            number: 3,
                            text: 'Set DDoS connection limit to >200 in router '
                                'settings (Security / DoS Protection).',
                          ),
                          _FixTile(
                            number: 4,
                            text:
                                'Use Bridged / NON-NAT network mode if running '
                                'inside a VM (VirtualBox, VMware, etc.).',
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(height: AppSpacing.md),

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

/// A diagnostic check tile used inside the Advanced Options section.
class _AdvancedCheckTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String description;

  const _AdvancedCheckTile({
    required this.icon,
    required this.title,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHighest.withValues(alpha: 0.4),
        borderRadius: BorderRadius.circular(AppRadius.sm),
        border: Border.all(
          color: colorScheme.outline.withValues(alpha: 0.15),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: colorScheme.tertiary),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: context.textStyles.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
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
    );
  }
}

/// A numbered common-fix suggestion tile.
class _FixTile extends StatelessWidget {
  final int number;
  final String text;

  const _FixTile({
    required this.number,
    required this.text,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 22,
            height: 22,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: colorScheme.tertiary.withValues(alpha: 0.15),
              shape: BoxShape.circle,
            ),
            child: Text(
              '$number',
              style: TextStyle(
                color: colorScheme.tertiary,
                fontWeight: FontWeight.bold,
                fontSize: 11,
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              text,
              style: context.textStyles.bodySmall?.withColor(
                colorScheme.onSurfaceVariant,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
