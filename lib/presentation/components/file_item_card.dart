import 'package:files/data/models/file_item.dart';
import 'package:files/theme.dart';
import 'package:flutter/material.dart';

class FileItemCard extends StatefulWidget {
  final FileItem file;
  final VoidCallback onTap;
  final VoidCallback? onDoubleTap;

  const FileItemCard({
    super.key,
    required this.file,
    required this.onTap,
    this.onDoubleTap,
  });

  @override
  State<FileItemCard> createState() => _FileItemCardState();
}

class _FileItemCardState extends State<FileItemCard> {
  bool _isHovered = false;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return MouseRegion(
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      child: GestureDetector(
        onTap: widget.onTap,
        onDoubleTap: widget.onDoubleTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          decoration: BoxDecoration(
            color: widget.file.isSelected
                ? colorScheme.primaryContainer.withValues(alpha: 0.3)
                : (_isHovered
                    ? colorScheme.surfaceContainerHighest.withValues(alpha: 0.5)
                    : Colors.transparent),
            borderRadius: BorderRadius.circular(AppRadius.sm),
            border: Border.all(
              color: widget.file.isSelected
                  ? colorScheme.primary
                  : (_isHovered
                      ? colorScheme.outline.withValues(alpha: 0.3)
                      : Colors.transparent),
              width: widget.file.isSelected ? 2 : 1,
            ),
          ),
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.sm,
            vertical: AppSpacing.xs,
          ),
          child: Row(
            children: [
              Icon(
                widget.file.isDirectory
                    ? Icons.folder
                    : Icons.insert_drive_file,
                color: widget.file.isDirectory
                    ? colorScheme.secondary
                    : colorScheme.onSurfaceVariant,
                size: 20,
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  widget.file.name,
                  style: context.textStyles.bodyMedium,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (!widget.file.isDirectory && widget.file.size != null) ...[
                const SizedBox(width: AppSpacing.sm),
                Text(
                  _formatBytes(widget.file.size!),
                  style: context.textStyles.bodySmall
                      ?.withColor(colorScheme.onSurfaceVariant),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) {
      return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    }
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }
}
