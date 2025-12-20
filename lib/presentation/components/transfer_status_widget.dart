import 'package:files/core/constants/enums.dart';
import 'package:files/data/models/transfer_task.dart';
import 'package:files/presentation/providers/transfer_provider.dart';
import 'package:files/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:provider/provider.dart';

class TransferStatusWidget extends StatelessWidget {
  const TransferStatusWidget({super.key});

  @override
  Widget build(BuildContext context) {
    final transferProvider = context.watch<TransferProvider>();
    final activeTasks = transferProvider.activeTasks;

    if (activeTasks.isEmpty) return const SizedBox.shrink();

    final colorScheme = Theme.of(context).colorScheme;

    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 400),
      child: Container(
        margin: AppSpacing.paddingMd,
        padding: AppSpacing.paddingMd,
        decoration: BoxDecoration(
          color: colorScheme.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: colorScheme.outline.withValues(alpha: 0.2)),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.1),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Icon(Icons.sync, color: colorScheme.primary, size: 20),
                const SizedBox(width: AppSpacing.sm),
                Text(
                  'Active Transfers',
                  style: context.textStyles.titleSmall?.semiBold,
                ),
                const Spacer(),
                IconButton(
                  icon: const Icon(Icons.clear_all, size: 18),
                  onPressed: transferProvider.clearCompleted,
                  tooltip: 'Clear completed',
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            ...activeTasks.map((task) => _TransferTaskItem(task: task)),
          ],
        ),
      )
        .animate()
        .fadeIn(duration: 300.ms)
        .slideY(begin: 0.2, end: 0),
    );
  }
}

class _TransferTaskItem extends StatelessWidget {
  final TransferTask task;

  const _TransferTaskItem({required this.task});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      padding: AppSpacing.paddingSm,
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                task.direction == TransferDirection.send
                    ? Icons.upload
                    : Icons.download,
                size: 16,
                color: colorScheme.primary,
              ),
              const SizedBox(width: AppSpacing.xs),
              Expanded(
                child: Text(
                  '${task.directionText} ${task.displayName}',
                  style: context.textStyles.bodySmall?.semiBold,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (task.status == TransferStatus.failed)
                Icon(Icons.error, size: 16, color: colorScheme.error),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: task.progress,
              backgroundColor: colorScheme.surfaceContainerHighest,
              color: task.status == TransferStatus.failed
                  ? colorScheme.error
                  : colorScheme.primary,
              minHeight: 4,
            ),
          ),
          if (task.errorMessage != null) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(
              task.errorMessage!,
              style: context.textStyles.bodySmall?.withColor(colorScheme.error),
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ],
      ),
    );
  }
}

class TransferHistorySheet extends StatelessWidget {
  const TransferHistorySheet({super.key});

  @override
  Widget build(BuildContext context) {
    final transferProvider = context.watch<TransferProvider>();
    final colorScheme = Theme.of(context).colorScheme;

    return Container(
      decoration: BoxDecoration(
        color: colorScheme.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: AppSpacing.paddingMd,
            child: Row(
              children: [
                Icon(Icons.history, color: colorScheme.primary),
                const SizedBox(width: AppSpacing.sm),
                Text(
                  'Transfer History',
                  style: context.textStyles.titleLarge?.semiBold,
                ),
                const Spacer(),
                IconButton(
                  icon: const Icon(Icons.delete_outline),
                  onPressed: () {
                    transferProvider.clearAll();
                    Navigator.pop(context);
                  },
                  tooltip: 'Clear all',
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: transferProvider.tasks.isEmpty
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.inbox,
                          size: 64,
                          color: colorScheme.onSurfaceVariant,
                        ),
                        const SizedBox(height: AppSpacing.md),
                        Text(
                          'No transfers yet',
                          style: context.textStyles.titleMedium,
                        ),
                      ],
                    ),
                  )
                : ListView.builder(
                    padding: AppSpacing.paddingMd,
                    itemCount: transferProvider.tasks.length,
                    itemBuilder: (context, index) {
                      final task = transferProvider.tasks[index];
                      return _HistoryTaskItem(task: task);
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _HistoryTaskItem extends StatelessWidget {
  final TransferTask task;

  const _HistoryTaskItem({required this.task});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final statusColor = task.status == TransferStatus.completed
        ? colorScheme.primary
        : task.status == TransferStatus.failed
            ? colorScheme.error
            : colorScheme.onSurfaceVariant;

    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: statusColor.withValues(alpha: 0.2),
          child: Icon(
            task.direction == TransferDirection.send
                ? Icons.upload
                : Icons.download,
            color: statusColor,
            size: 20,
          ),
        ),
        title: Text(task.displayName),
        subtitle: Text(
          '${task.directionText} • ${_formatTime(task.createdAt)}',
          style: context.textStyles.bodySmall,
        ),
        trailing: Icon(
          task.status == TransferStatus.completed
              ? Icons.check_circle
              : task.status == TransferStatus.failed
                  ? Icons.error
                  : Icons.pending,
          color: statusColor,
        ),
      ),
    );
  }

  String _formatTime(DateTime time) {
    final now = DateTime.now();
    final diff = now.difference(time);

    if (diff.inMinutes < 1) return 'Just now';
    if (diff.inHours < 1) return '${diff.inMinutes}m ago';
    if (diff.inDays < 1) return '${diff.inHours}h ago';
    return '${diff.inDays}d ago';
  }
}
