import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import 'package:lanfxplorer/data/services/api_service.dart';
import 'package:lanfxplorer/presentation/dialogs/troubleshoot_dialog.dart';
import 'package:lanfxplorer/presentation/dialogs/update_dialog.dart';
import 'package:lanfxplorer/presentation/providers/env_provider.dart';
import 'package:lanfxplorer/presentation/providers/session_provider.dart';
import 'package:lanfxplorer/theme.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  // ── Password ──────────────────────────────────────────────────────────────
  final _newPasswordCtrl = TextEditingController();
  bool _showNewPassword = false;
  bool _isChangingPassword = false;
  String? _passwordMsg;
  bool _passwordSuccess = false;

  // ── Interfaces ────────────────────────────────────────────────────────────
  List<Map<String, dynamic>> _interfaces = [];
  String? _selectedInterface;
  bool _isLoadingInterfaces = true;
  bool _isSavingInterface = false;

  @override
  void initState() {
    super.initState();
    _loadInterfaces();
    // Pre-fill selected interface from env
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final iface = context.read<EnvProvider>().env?.interface;
      if (iface != null && iface.isNotEmpty) {
        setState(() => _selectedInterface = iface);
      }
    });
  }

  @override
  void dispose() {
    _newPasswordCtrl.dispose();
    super.dispose();
  }

  // ── Interface loading ─────────────────────────────────────────────────────
  Future<void> _loadInterfaces() async {
    setState(() => _isLoadingInterfaces = true);
    try {
      final api = context.read<ApiService>();
      final ifaces = await api.getInterfaces();
      if (!mounted) return;
      setState(() {
        _interfaces = ifaces;
        _isLoadingInterfaces = false;
        // If nothing selected yet, pick the current active one
        if (_selectedInterface == null) {
          for (final i in ifaces) {
            if (i['active'] == true) {
              _selectedInterface = i['name'] as String?;
              break;
            }
          }
          _selectedInterface ??= ifaces.isNotEmpty ? ifaces.first['name'] as String? : null;
        }
      });
    } catch (_) {
      if (mounted) setState(() => _isLoadingInterfaces = false);
    }
  }

  Future<void> _applyInterface() async {
    if (_selectedInterface == null) return;
    setState(() => _isSavingInterface = true);
    final api = context.read<ApiService>();
    final ok  = await api.setInterface(_selectedInterface!);
    if (!mounted) return;
    if (ok) await context.read<EnvProvider>().updateInterface(_selectedInterface!);
    setState(() => _isSavingInterface = false);
    _showSnack(ok ? 'Interface set to $_selectedInterface' : 'Failed to set interface', isError: !ok);
  }

  // ── Directory pickers ─────────────────────────────────────────────────────
  Future<void> _pickOutDir() async {
    final result = await FilePicker.platform.getDirectoryPath(
      dialogTitle: 'Select Receive Directory (OUTDIR)',
    );
    if (result == null || !mounted) return;
    final env = context.read<EnvProvider>();
    await env.updateOutDir(result);
    final api = context.read<ApiService>();
    await api.updateDirs(outDir: result);
    _showSnack('Receive directory updated');
  }

  Future<void> _pickSrcDir() async {
    final result = await FilePicker.platform.getDirectoryPath(
      dialogTitle: 'Select Source Directory (SRCDIR)',
    );
    if (result == null || !mounted) return;
    final env = context.read<EnvProvider>();
    await env.updateSrcDir(result);
    final api = context.read<ApiService>();
    await api.updateDirs(srcDir: result);
    _showSnack('Source directory updated');
  }

  // ── Password change ───────────────────────────────────────────────────────
  Future<void> _changePassword() async {
    final newPwd = _newPasswordCtrl.text.trim();
    if (newPwd.isEmpty) {
      setState(() { _passwordMsg = 'Enter a new password'; _passwordSuccess = false; });
      return;
    }
    setState(() { _isChangingPassword = true; _passwordMsg = null; });
    try {
      final api = context.read<ApiService>();
      final ok  = await api.setPassword(newPwd);
      if (!mounted) return;
      setState(() {
        _isChangingPassword = false;
        _passwordSuccess = ok;
        _passwordMsg = ok ? 'Password updated successfully' : 'Failed to update password';
      });
      if (ok) _newPasswordCtrl.clear();
    } catch (e) {
      if (!mounted) return;
      setState(() { _isChangingPassword = false; _passwordMsg = 'Error: $e'; _passwordSuccess = false; });
    }
  }

  // ── Sign out ──────────────────────────────────────────────────────────────
  Future<void> _signOut() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Sign Out'),
        content: const Text('Are you sure you want to sign out?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Theme.of(ctx).colorScheme.error),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Sign Out'),
          ),
        ],
      ),
    );
    if (confirmed == true && mounted) {
      await context.read<EnvProvider>().logout();
      context.read<SessionProvider>().endSession();
      if (mounted) context.go('/');
    }
  }

  void _showSnack(String msg, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      behavior: SnackBarBehavior.floating,
      duration: const Duration(seconds: 2),
      backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
    ));
  }

  // ── Build ──────────────────────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final env = context.watch<EnvProvider>().env;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      body: Column(
        children: [
          // ── Custom header ─────────────────────────────────────────────────
          Container(
            padding: const EdgeInsets.fromLTRB(8, 8, 16, 8),
            decoration: BoxDecoration(
              color: colorScheme.surface,
              border: Border(
                bottom: BorderSide(color: colorScheme.outline.withValues(alpha: 0.15)),
              ),
            ),
            child: Row(
              children: [
                IconButton(
                  icon: const Icon(Icons.arrow_back),
                  onPressed: () => context.pop(),
                  tooltip: 'Back',
                ),
                const SizedBox(width: AppSpacing.sm),
                Icon(Icons.settings_rounded, color: colorScheme.primary, size: 24),
                const SizedBox(width: AppSpacing.sm),
                Text('Settings', style: context.textStyles.titleLarge?.semiBold),
                const Spacer(),
                // ── Update button ────────────────────────────────────────
                OutlinedButton.icon(
                  onPressed: () => showDialog(
                    context: context,
                    barrierDismissible: false,
                    builder: (_) => const UpdateDialog(),
                  ),
                  icon: const Icon(Icons.system_update_rounded, size: 16),
                  label: const Text('Update'),
                  style: OutlinedButton.styleFrom(
                    side: BorderSide(
                        color: colorScheme.primary.withValues(alpha: 0.5)),
                    foregroundColor: colorScheme.primary,
                    visualDensity: VisualDensity.compact,
                  ),
                ),
              ],
            ),
          ).animate().fadeIn(duration: 200.ms),

          // ── Scrollable body ───────────────────────────────────────────────
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(AppSpacing.lg),
              children: [

                // ═══════════════════════════════════════
                //  SECTION 1 — Profile & Directories
                // ═══════════════════════════════════════
                _SectionHeader(icon: Icons.person_rounded, label: 'Profile & Directories'),
                const SizedBox(height: AppSpacing.md),

                // OUTDIR picker
                _DirPickerTile(
                  icon: Icons.download_rounded,
                  label: 'Receive Directory (OUTDIR)',
                  description: 'Files received from peers are saved here',
                  currentPath: env?.outDir ?? '—',
                  onPick: _pickOutDir,
                ).animate().fadeIn(duration: 250.ms, delay: 50.ms).slideY(begin: 0.05, end: 0),

                const SizedBox(height: AppSpacing.sm),

                // SRCDIR picker
                _DirPickerTile(
                  icon: Icons.drive_folder_upload_rounded,
                  label: 'Source Directory (SRCDIR)',
                  description: 'Default folder shown when browsing your files',
                  currentPath: env?.srcDir ?? '—',
                  onPick: _pickSrcDir,
                ).animate().fadeIn(duration: 250.ms, delay: 100.ms).slideY(begin: 0.05, end: 0),

                const SizedBox(height: AppSpacing.lg),

                // Password change
                _SettingsCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(children: [
                        Icon(Icons.lock_rounded, color: colorScheme.primary, size: 20),
                        const SizedBox(width: AppSpacing.sm),
                        Text('Change Password', style: context.textStyles.titleSmall?.semiBold),
                      ]),
                      const SizedBox(height: AppSpacing.sm),
                      Text(
                        'Password is used by peers to authenticate with you',
                        style: context.textStyles.bodySmall?.withColor(colorScheme.onSurfaceVariant),
                      ),
                      const SizedBox(height: AppSpacing.md),
                      TextField(
                        controller: _newPasswordCtrl,
                        obscureText: !_showNewPassword,
                        decoration: InputDecoration(
                          labelText: 'New Password',
                          border: const OutlineInputBorder(),
                          suffixIcon: IconButton(
                            icon: Icon(_showNewPassword ? Icons.visibility_off : Icons.visibility),
                            onPressed: () => setState(() => _showNewPassword = !_showNewPassword),
                          ),
                        ),
                      ),
                      if (_passwordMsg != null) ...[
                        const SizedBox(height: AppSpacing.sm),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: AppSpacing.md, vertical: AppSpacing.sm),
                          decoration: BoxDecoration(
                            color: _passwordSuccess
                                ? colorScheme.primaryContainer
                                : colorScheme.errorContainer,
                            borderRadius: BorderRadius.circular(AppRadius.sm),
                          ),
                          child: Row(children: [
                            Icon(
                              _passwordSuccess ? Icons.check_circle : Icons.error,
                              size: 16,
                              color: _passwordSuccess
                                  ? colorScheme.onPrimaryContainer
                                  : colorScheme.onErrorContainer,
                            ),
                            const SizedBox(width: AppSpacing.sm),
                            Expanded(child: Text(
                              _passwordMsg!,
                              style: context.textStyles.bodySmall?.copyWith(
                                color: _passwordSuccess
                                    ? colorScheme.onPrimaryContainer
                                    : colorScheme.onErrorContainer,
                              ),
                            )),
                          ]),
                        ).animate().fadeIn(duration: 200.ms),
                      ],
                      const SizedBox(height: AppSpacing.md),
                      Align(
                        alignment: Alignment.centerRight,
                        child: FilledButton.icon(
                          onPressed: _isChangingPassword ? null : _changePassword,
                          icon: _isChangingPassword
                              ? const SizedBox(
                                  width: 16, height: 16,
                                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                              : const Icon(Icons.save_rounded, size: 18),
                          label: Text(_isChangingPassword ? 'Saving…' : 'Save Password'),
                        ),
                      ),
                    ],
                  ),
                ).animate().fadeIn(duration: 250.ms, delay: 150.ms),

                const SizedBox(height: AppSpacing.xl),

                // ═══════════════════════════════════════
                //  SECTION 2 — Network Interface
                // ═══════════════════════════════════════
                _SectionHeader(icon: Icons.swap_horiz_rounded, label: 'Network Interface'),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'Select the interface to use for peer discovery and file transfer. '
                  'Loopback (lo) is excluded.',
                  style: context.textStyles.bodySmall?.withColor(colorScheme.onSurfaceVariant),
                ),
                const SizedBox(height: AppSpacing.md),

                _SettingsCard(
                  child: _isLoadingInterfaces
                      ? const Padding(
                          padding: EdgeInsets.all(AppSpacing.lg),
                          child: Center(child: CircularProgressIndicator()),
                        )
                      : _interfaces.isEmpty
                          ? Padding(
                              padding: const EdgeInsets.all(AppSpacing.md),
                              child: Row(children: [
                                Icon(Icons.wifi_off, color: colorScheme.onSurfaceVariant),
                                const SizedBox(width: AppSpacing.sm),
                                Text(
                                  'No interfaces found',
                                  style: context.textStyles.bodyMedium
                                      ?.withColor(colorScheme.onSurfaceVariant),
                                ),
                              ]),
                            )
                          : Column(
                              children: [
                                ..._interfaces.asMap().entries.map((entry) {
                                  final iface = entry.value['name'] as String;
                                  final isSelected = _selectedInterface == iface;
                                  return RadioListTile<String>(
                                    value: iface,
                                    groupValue: _selectedInterface,
                                    onChanged: (v) => setState(() => _selectedInterface = v),
                                    title: Row(children: [
                                      Icon(
                                        _ifaceIcon(iface),
                                        size: 20,
                                        color: isSelected
                                            ? colorScheme.primary
                                            : colorScheme.onSurfaceVariant,
                                      ),
                                      const SizedBox(width: AppSpacing.sm),
                                      Text(
                                        iface,
                                        style: context.textStyles.bodyMedium?.copyWith(
                                          fontWeight: isSelected ? FontWeight.w600 : null,
                                          color: isSelected ? colorScheme.primary : null,
                                        ),
                                      ),
                                      if (entry.value['active'] == true) ...[
                                        const SizedBox(width: AppSpacing.sm),
                                        Container(
                                          padding: const EdgeInsets.symmetric(
                                              horizontal: 6, vertical: 2),
                                          decoration: BoxDecoration(
                                            color: colorScheme.primaryContainer,
                                            borderRadius: BorderRadius.circular(8),
                                          ),
                                          child: Text(
                                            'active',
                                            style: context.textStyles.bodySmall?.copyWith(
                                              color: colorScheme.onPrimaryContainer,
                                              fontSize: 10,
                                              fontWeight: FontWeight.w600,
                                            ),
                                          ),
                                        ),
                                      ],
                                    ]),
                                    contentPadding: EdgeInsets.zero,
                                  );
                                }),
                                const Divider(height: 1),
                                Padding(
                                  padding: const EdgeInsets.only(top: AppSpacing.md),
                                  child: Row(
                                    mainAxisAlignment: MainAxisAlignment.end,
                                    children: [
                                      OutlinedButton.icon(
                                        onPressed: _isLoadingInterfaces ? null : _loadInterfaces,
                                        icon: const Icon(Icons.refresh, size: 16),
                                        label: const Text('Refresh'),
                                      ),
                                      const SizedBox(width: AppSpacing.sm),
                                      FilledButton.icon(
                                        onPressed: _isSavingInterface ? null : _applyInterface,
                                        icon: _isSavingInterface
                                            ? const SizedBox(
                                                width: 16, height: 16,
                                                child: CircularProgressIndicator(
                                                    strokeWidth: 2, color: Colors.white))
                                            : const Icon(Icons.check_rounded, size: 18),
                                        label: Text(_isSavingInterface ? 'Applying…' : 'Apply'),
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                ).animate().fadeIn(duration: 250.ms, delay: 200.ms),

                const SizedBox(height: AppSpacing.xl),

                // ═══════════════════════════════════════
                //  SECTION 3 — Troubleshoot
                // ═══════════════════════════════════════
                _SectionHeader(icon: Icons.build_circle_rounded, label: 'Troubleshoot'),
                const SizedBox(height: AppSpacing.md),

                _SettingsCard(
                  child: Row(children: [
                    Expanded(child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Connection Issues?', style: context.textStyles.titleSmall?.semiBold),
                        const SizedBox(height: 4),
                        Text(
                          'Step-by-step network diagnostics and firewall fix',
                          style: context.textStyles.bodySmall
                              ?.withColor(colorScheme.onSurfaceVariant),
                        ),
                      ],
                    )),
                    const SizedBox(width: AppSpacing.md),
                    OutlinedButton.icon(
                      onPressed: () => showDialog(
                        context: context,
                        builder: (ctx) => TroubleshootDialog(
                          apiService: context.read<ApiService>(),
                        ),
                      ),
                      icon: const Icon(Icons.open_in_new, size: 16),
                      label: const Text('Open'),
                    ),
                  ]),
                ).animate().fadeIn(duration: 250.ms, delay: 250.ms),

                const SizedBox(height: AppSpacing.xl),

                // ═══════════════════════════════════════
                //  SECTION 4 — Sign Out (destructive)
                // ═══════════════════════════════════════
                const Divider(),
                const SizedBox(height: AppSpacing.md),

                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: _signOut,
                    icon: Icon(Icons.logout_rounded, color: colorScheme.error),
                    label: Text('Sign Out', style: TextStyle(color: colorScheme.error)),
                    style: OutlinedButton.styleFrom(
                      side: BorderSide(color: colorScheme.error.withValues(alpha: 0.5)),
                      padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
                    ),
                  ),
                ).animate().fadeIn(duration: 250.ms, delay: 300.ms),

                const SizedBox(height: AppSpacing.lg),
              ],
            ),
          ),
        ],
      ),
    );
  }

  IconData _ifaceIcon(String name) {
    if (name.startsWith('wlan') || name.startsWith('wlp') || name.startsWith('wifi')) {
      return Icons.wifi;
    }
    if (name.startsWith('eth') || name.startsWith('enp') || name.startsWith('eno')) {
      return Icons.cable;
    }
    return Icons.device_hub;
  }
}

// ── Reusable sub-widgets ────────────────────────────────────────────────────

class _SectionHeader extends StatelessWidget {
  final IconData icon;
  final String label;
  const _SectionHeader({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Row(children: [
      Icon(icon, size: 18, color: colorScheme.primary),
      const SizedBox(width: AppSpacing.sm),
      Text(
        label.toUpperCase(),
        style: context.textStyles.labelMedium?.copyWith(
          color: colorScheme.primary,
          fontWeight: FontWeight.w700,
          letterSpacing: 1.2,
        ),
      ),
    ]);
  }
}

class _SettingsCard extends StatelessWidget {
  final Widget child;
  const _SettingsCard({required this.child});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHighest.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(color: colorScheme.outline.withValues(alpha: 0.15)),
      ),
      child: child,
    );
  }
}

class _DirPickerTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final String description;
  final String currentPath;
  final VoidCallback onPick;

  const _DirPickerTile({
    required this.icon,
    required this.label,
    required this.description,
    required this.currentPath,
    required this.onPick,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return _SettingsCard(
      child: Row(
        children: [
          Icon(icon, color: colorScheme.primary, size: 20),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: context.textStyles.bodyMedium?.semiBold),
                const SizedBox(height: 2),
                Text(description,
                    style: context.textStyles.bodySmall
                        ?.withColor(colorScheme.onSurfaceVariant)),
                const SizedBox(height: 4),
                Text(
                  currentPath,
                  style: context.textStyles.bodySmall?.copyWith(
                    fontFamily: 'monospace',
                    color: colorScheme.primary,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          OutlinedButton.icon(
            onPressed: onPick,
            icon: const Icon(Icons.folder_open, size: 16),
            label: const Text('Change'),
          ),
        ],
      ),
    );
  }
}
