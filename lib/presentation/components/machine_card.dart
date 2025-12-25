import 'package:lanfxplorer/data/models/machine.dart';
import 'package:lanfxplorer/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

class MachineCard extends StatefulWidget {
  final Machine machine;
  final VoidCallback onTap;

  const MachineCard({
    super.key,
    required this.machine,
    required this.onTap,
  });

  @override
  State<MachineCard> createState() => _MachineCardState();
}

class _MachineCardState extends State<MachineCard> {
  bool _isHovered = false;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return MouseRegion(
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          decoration: BoxDecoration(
            color: colorScheme.surface,
            borderRadius: BorderRadius.circular(AppRadius.md),
            border: Border.all(
              color: _isHovered
                  ? colorScheme.primary
                  : colorScheme.outline.withValues(alpha: 0.2),
              width: _isHovered ? 2 : 1,
            ),
          ),
          padding: AppSpacing.paddingMd,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.computer,
                size: 48,
                color: colorScheme.primary,
              ),
              const SizedBox(height: AppSpacing.md),
              Text(
                widget.machine.username,
                style: context.textStyles.titleMedium?.semiBold,
                textAlign: TextAlign.center,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: AppSpacing.xs),
              Text(
                widget.machine.ipAddress,
                style: context.textStyles.bodySmall
                    ?.withColor(colorScheme.onSurfaceVariant),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: AppSpacing.sm),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color:
                          widget.machine.isOnline ? Colors.green : Colors.grey,
                      shape: BoxShape.circle,
                    ),
                  )
                      .animate(onPlay: (controller) => controller.repeat())
                      .fadeIn(duration: 1000.ms)
                      .then()
                      .fadeOut(duration: 1000.ms),
                  const SizedBox(width: AppSpacing.xs),
                  Text(
                    widget.machine.isOnline ? 'Online' : 'Offline',
                    style: context.textStyles.labelSmall
                        ?.withColor(colorScheme.onSurfaceVariant),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
