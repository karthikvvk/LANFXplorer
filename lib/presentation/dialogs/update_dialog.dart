import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:provider/provider.dart';

import 'package:lanfxplorer/data/services/api_service.dart';
import 'package:lanfxplorer/theme.dart';

/// Full smart-update dialog.
///
/// States:
///   checking  →  up_to_date | update_available | error
///   (user taps Apply) → applying → done | apply_error
class UpdateDialog extends StatefulWidget {
  const UpdateDialog({super.key});

  @override
  State<UpdateDialog> createState() => _UpdateDialogState();
}

enum _UpdateState {
  checking,
  upToDate,
  updateAvailable,
  applying,
  done,
  error,
}

class _UpdateDialogState extends State<UpdateDialog> {
  _UpdateState _state = _UpdateState.checking;
  Map<String, dynamic>? _info;  // from checkUpdate
  String? _errorMsg;
  String? _newSha;

  @override
  void initState() {
    super.initState();
    _checkForUpdate();
  }

  Future<void> _checkForUpdate() async {
    setState(() => _state = _UpdateState.checking);
    final api    = context.read<ApiService>();
    final result = await api.checkUpdate();
    if (!mounted) return;

    if (result == null || result.containsKey('error')) {
      setState(() {
        _state    = _UpdateState.error;
        _errorMsg = result?['error'] ?? 'Could not reach GitHub. Check network or token.';
      });
      return;
    }

    setState(() {
      _info  = result;
      _state = (result['is_latest'] == true)
          ? _UpdateState.upToDate
          : _UpdateState.updateAvailable;
    });
  }

  Future<void> _applyUpdate() async {
    setState(() => _state = _UpdateState.applying);
    final api    = context.read<ApiService>();
    final result = await api.applyUpdate();
    if (!mounted) return;

    if (result['success'] == true) {
      setState(() {
        _state  = _UpdateState.done;
        _newSha = result['short'] as String?;
      });
    } else {
      setState(() {
        _state    = _UpdateState.error;
        _errorMsg = result['error']?.toString() ?? 'Update failed';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Dialog(
      shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.lg)),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 440),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // ── Title ────────────────────────────────────────────────────
              Row(children: [
                Icon(Icons.system_update_rounded,
                    color: colorScheme.primary, size: 26),
                const SizedBox(width: AppSpacing.sm),
                Text('Software Update',
                    style: context.textStyles.titleLarge?.semiBold),
                const Spacer(),
                IconButton(
                  icon: const Icon(Icons.close),
                  onPressed: () => Navigator.pop(context),
                  visualDensity: VisualDensity.compact,
                ),
              ]),
              const SizedBox(height: AppSpacing.lg),

              // ── Body ─────────────────────────────────────────────────────
              _buildBody(colorScheme),

              const SizedBox(height: AppSpacing.lg),

              // ── Actions ──────────────────────────────────────────────────
              _buildActions(colorScheme),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildBody(ColorScheme cs) {
    switch (_state) {
      // ── Checking ──────────────────────────────────────────────────────────
      case _UpdateState.checking:
        return Column(children: [
          const LinearProgressIndicator(),
          const SizedBox(height: AppSpacing.md),
          Text('Checking for updates…',
              style: context.textStyles.bodyMedium
                  ?.withColor(cs.onSurfaceVariant)),
        ]).animate().fadeIn(duration: 200.ms);

      // ── Up to date ────────────────────────────────────────────────────────
      case _UpdateState.upToDate:
        return _StatusTile(
          icon: Icons.check_circle_rounded,
          iconColor: Colors.green,
          title: 'You\'re up to date',
          subtitle: 'Installed: ${_info?['short_local'] ?? '—'}',
        ).animate().fadeIn(duration: 250.ms).slideY(begin: 0.05, end: 0);

      // ── Update available ──────────────────────────────────────────────────
      case _UpdateState.updateAvailable:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _StatusTile(
              icon: Icons.new_releases_rounded,
              iconColor: cs.primary,
              title: 'Update available!',
              subtitle: '${_info?['short_local'] ?? '—'} → ${_info?['short_latest'] ?? '—'}',
            ),
            const SizedBox(height: AppSpacing.md),
            _InfoRow(label: 'Latest commit',
                value: _info?['commit_message'] ?? ''),
            const SizedBox(height: AppSpacing.xs),
            _InfoRow(label: 'Date',
                value: _fmtDate(_info?['commit_date'])),
            const SizedBox(height: AppSpacing.md),
            Container(
              padding: const EdgeInsets.all(AppSpacing.sm),
              decoration: BoxDecoration(
                color: cs.primaryContainer.withValues(alpha: 0.4),
                borderRadius: BorderRadius.circular(AppRadius.sm),
              ),
              child: Row(children: [
                Icon(Icons.info_outline, size: 16, color: cs.onPrimaryContainer),
                const SizedBox(width: AppSpacing.xs),
                Expanded(child: Text(
                  'Your .env, certs, and virtual/ will NOT be touched.',
                  style: context.textStyles.bodySmall
                      ?.withColor(cs.onPrimaryContainer),
                )),
              ]),
            ),
          ],
        ).animate().fadeIn(duration: 250.ms).slideY(begin: 0.05, end: 0);

      // ── Applying ──────────────────────────────────────────────────────────
      case _UpdateState.applying:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const LinearProgressIndicator(),
            const SizedBox(height: AppSpacing.md),
            Text('Applying update…',
                style: context.textStyles.titleSmall?.semiBold),
            const SizedBox(height: AppSpacing.xs),
            Text('Downloading archive, copying files, upgrading packages.\n'
                'This may take up to 2 minutes.',
                style: context.textStyles.bodySmall
                    ?.withColor(cs.onSurfaceVariant)),
          ],
        ).animate().fadeIn(duration: 200.ms);

      // ── Done ──────────────────────────────────────────────────────────────
      case _UpdateState.done:
        return _StatusTile(
          icon: Icons.celebration_rounded,
          iconColor: Colors.green,
          title: 'Update applied!',
          subtitle: 'Now on: ${_newSha ?? '—'}\nRestart the app to load new code.',
        ).animate().fadeIn(duration: 300.ms).scale(begin: const Offset(0.95, 0.95));

      // ── Error ─────────────────────────────────────────────────────────────
      case _UpdateState.error:
        return _StatusTile(
          icon: Icons.error_rounded,
          iconColor: cs.error,
          title: 'Failed',
          subtitle: _errorMsg ?? 'Unknown error',
        ).animate().fadeIn(duration: 200.ms);
    }
  }

  Widget _buildActions(ColorScheme cs) {
    switch (_state) {
      case _UpdateState.checking:
      case _UpdateState.applying:
        return const SizedBox.shrink();

      case _UpdateState.upToDate:
      case _UpdateState.done:
        return Align(
          alignment: Alignment.centerRight,
          child: FilledButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close'),
          ),
        );

      case _UpdateState.updateAvailable:
        return Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            OutlinedButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Later'),
            ),
            const SizedBox(width: AppSpacing.sm),
            FilledButton.icon(
              onPressed: _applyUpdate,
              icon: const Icon(Icons.download_rounded, size: 18),
              label: const Text('Update Now'),
            ),
          ],
        );

      case _UpdateState.error:
        return Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            OutlinedButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Close'),
            ),
            const SizedBox(width: AppSpacing.sm),
            FilledButton.icon(
              onPressed: _checkForUpdate,
              icon: const Icon(Icons.refresh, size: 18),
              label: const Text('Retry'),
            ),
          ],
        );
    }
  }

  String _fmtDate(String? iso) {
    if (iso == null) return '—';
    try {
      final dt = DateTime.parse(iso).toLocal();
      return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-'
          '${dt.day.toString().padLeft(2, '0')} '
          '${dt.hour.toString().padLeft(2, '0')}:'
          '${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      return iso;
    }
  }
}

// ── Reusable sub-widgets ─────────────────────────────────────────────────────

class _StatusTile extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String title;
  final String subtitle;
  const _StatusTile({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.subtitle,
  });

  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Icon(icon, color: iconColor, size: 32),
      const SizedBox(width: AppSpacing.md),
      Expanded(child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style: context.textStyles.titleMedium?.semiBold),
          const SizedBox(height: 4),
          Text(subtitle,
              style: context.textStyles.bodySmall
                  ?.withColor(Theme.of(context).colorScheme.onSurfaceVariant)),
        ],
      )),
    ],
  );
}

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;
  const _InfoRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      SizedBox(
        width: 100,
        child: Text(label,
            style: context.textStyles.bodySmall?.copyWith(
              fontWeight: FontWeight.w600,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            )),
      ),
      Expanded(child: Text(value,
          style: context.textStyles.bodySmall
              ?.withColor(Theme.of(context).colorScheme.onSurface),
          maxLines: 2,
          overflow: TextOverflow.ellipsis)),
    ],
  );
}
