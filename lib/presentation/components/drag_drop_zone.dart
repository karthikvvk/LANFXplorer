import 'package:desktop_drop/desktop_drop.dart';
import 'package:lanfxplorer/theme.dart';
import 'package:flutter/material.dart';

class DragDropZone extends StatefulWidget {
  final Widget child;
  final bool enabled;
  final void Function(List<String> paths)? onFilesDropped;

  const DragDropZone({
    super.key,
    required this.child,
    this.enabled = true,
    this.onFilesDropped,
  });

  @override
  State<DragDropZone> createState() => _DragDropZoneState();
}

class _DragDropZoneState extends State<DragDropZone> {
  bool _isDragging = false;

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) return widget.child;

    final colorScheme = Theme.of(context).colorScheme;

    return DropTarget(
      onDragEntered: (_) => setState(() => _isDragging = true),
      onDragExited: (_) => setState(() => _isDragging = false),
      onDragDone: (details) {
        setState(() => _isDragging = false);
        final paths = details.files.map((f) => f.path).toList();
        widget.onFilesDropped?.call(paths);
      },
      child: Stack(
        children: [
          widget.child,
          if (_isDragging)
            Positioned.fill(
              child: Container(
                decoration: BoxDecoration(
                  color: colorScheme.primary.withValues(alpha: 0.1),
                  border: Border.all(
                    color: colorScheme.primary,
                    width: 3,
                  ),
                ),
                child: Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.file_upload,
                        size: 64,
                        color: colorScheme.primary,
                      ),
                      const SizedBox(height: AppSpacing.md),
                      Text(
                        'Drop files here',
                        style: context.textStyles.headlineSmall?.copyWith(
                          color: colorScheme.primary,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
