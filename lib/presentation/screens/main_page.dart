import 'package:files/core/utils/logger.dart';
import 'package:files/data/services/api_service.dart';
import 'package:files/presentation/components/drag_drop_zone.dart';
import 'package:files/presentation/components/file_item_card.dart';
import 'package:files/presentation/components/theme_toggle_button.dart';
import 'package:files/presentation/components/transfer_status_widget.dart';
import 'package:files/presentation/providers/env_provider.dart';
import 'package:files/presentation/providers/file_system_provider.dart';
import 'package:files/presentation/providers/session_provider.dart';
import 'package:files/presentation/providers/transfer_provider.dart';
import 'package:files/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

class MainPage extends StatefulWidget {
  const MainPage({super.key});

  @override
  State<MainPage> createState() => _MainPageState();
}

class _MainPageState extends State<MainPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final envProvider = context.read<EnvProvider>();
      final fileSystemProvider = context.read<FileSystemProvider>();
      final destIp = envProvider.env?.destHost;

      // Set root path from outDir (the directory user selected on login)
      final rootPath = envProvider.env?.outDir;
      if (rootPath != null && rootPath.isNotEmpty) {
        fileSystemProvider.setRootPath(rootPath);
        AppLogger.info('MainPage: Root path set to: $rootPath');
      }

      // Load files starting from root path
      fileSystemProvider.loadLocalFiles(rootPath ?? ".");

      AppLogger.info('MainPage: Initializing. Destination IP: $destIp');

      fileSystemProvider.loadRemoteFiles(
        rootPath ?? ".",
        destIp,
      );
    });
  }

  Future<void> _onSendToDest() async {
    final fileSystemProvider = context.read<FileSystemProvider>();
    final transferProvider = context.read<TransferProvider>();
    final selectedFiles = fileSystemProvider.selectedLocalFiles;

    if (selectedFiles.isEmpty) {
      _showSnackBar('No files selected to send');
      return;
    }

    final destId = context.read<EnvProvider>().env?.destHost;
    if (destId == null || destId.isEmpty) {
      _showSnackBar('No destination machine connected');
      return;
    }

    // Get the current remote directory path as the destination
    final destDir = fileSystemProvider.remoteCurrentPath;

    AppLogger.transfer(
        'Sending ${selectedFiles.length} files to $destId at $destDir');
    final success = await transferProvider.sendFiles(destId, selectedFiles,
        destDir: destDir);

    if (success) {
      _showSnackBar('Successfully sent ${selectedFiles.length} file(s)');
      fileSystemProvider.clearLocalSelection();
    } else {
      _showSnackBar('Failed to send files', isError: true);
    }
  }

  Future<void> _onFetchFromDest() async {
    final fileSystemProvider = context.read<FileSystemProvider>();
    final transferProvider = context.read<TransferProvider>();
    final selectedFiles = fileSystemProvider.selectedRemoteFiles;

    if (selectedFiles.isEmpty) {
      _showSnackBar('No files selected to fetch');
      return;
    }

    final sourceId = context.read<EnvProvider>().env?.destHost;
    if (sourceId == null || sourceId.isEmpty) {
      _showSnackBar('No source machine connected');
      return;
    }

    // Get the local current directory as the destination
    final destDir = fileSystemProvider.localCurrentPath;

    AppLogger.transfer(
        'Fetching ${selectedFiles.length} files from $sourceId to $destDir');
    final success = await transferProvider.fetchFiles(sourceId, selectedFiles,
        destDir: destDir);

    if (success) {
      _showSnackBar('Successfully fetched ${selectedFiles.length} file(s)');
      fileSystemProvider.clearRemoteSelection();
      await fileSystemProvider.loadLocalFiles();
    } else {
      _showSnackBar('Failed to fetch files', isError: true);
    }
  }

  void _onHome() {
    context.read<SessionProvider>().endSession();
    context.go('/home');
  }

  void _onLogout() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Sign Out'),
        content: const Text('Are you sure you want to sign out?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Sign Out'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      await context.read<EnvProvider>().logout();
      context.read<SessionProvider>().endSession();
      if (mounted) {
        context.go('/');
      }
    }
  }

  void _onReconnect() async {
    final session = context.read<SessionProvider>();
    final api = context.read<ApiService>();

    final ok = await session.reconnect(api);

    _showSnackBar(
      ok ? 'Reconnected successfully' : 'Server not reachable',
    );
  }

  void _showSnackBar(String message, {bool isError = false}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 2),
        backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
      ),
    );
  }

  void _showTransferHistory() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) => SizedBox(
        height: MediaQuery.of(context).size.height * 0.7,
        child: const TransferHistorySheet(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final sessionProvider = context.watch<SessionProvider>();

    return Scaffold(
      body: Column(
        children: [
          // Toolbar Header
          Container(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.sm,
            ),
            decoration: BoxDecoration(
              color: colorScheme.surface,
              border: Border(
                bottom: BorderSide(
                  color: colorScheme.outline.withValues(alpha: 0.2),
                  width: 1,
                ),
              ),
            ),
            child: Row(
              children: [
                Icon(Icons.folder_shared, color: colorScheme.primary, size: 28),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Connected to ${sessionProvider.destinationMachine?.username ?? "Unknown"}',
                        style: context.textStyles.titleMedium?.semiBold,
                      ),
                      Text(
                        sessionProvider.destinationMachine?.ipAddress ?? '',
                        style: context.textStyles.bodySmall
                            ?.withColor(colorScheme.onSurfaceVariant),
                      ),
                    ],
                  ),
                ),
                _ToolbarButton(
                  icon: Icons.send,
                  label: 'Send',
                  onPressed: _onSendToDest,
                ),
                const SizedBox(width: AppSpacing.xs),
                _ToolbarButton(
                  icon: Icons.download,
                  label: 'Fetch',
                  onPressed: _onFetchFromDest,
                ),
                const SizedBox(width: AppSpacing.xs),
                _ToolbarButton(
                  icon: Icons.refresh,
                  label: 'Reconnect',
                  onPressed: _onReconnect,
                ),
                const SizedBox(width: AppSpacing.xs),
                _ToolbarButton(
                  icon: Icons.history,
                  label: 'History',
                  onPressed: _showTransferHistory,
                ),
                const SizedBox(width: AppSpacing.xs),
                _ToolbarButton(
                  icon: Icons.home,
                  label: 'Home',
                  onPressed: _onHome,
                ),
                const SizedBox(width: AppSpacing.xs),
                _ToolbarButton(
                  icon: Icons.logout,
                  label: 'Sign Out',
                  onPressed: _onLogout,
                  isDestructive: true,
                ),
                const SizedBox(width: AppSpacing.sm),
                const ThemeToggleButton(),
              ],
            ),
          ),

          // Dual-pane file explorer
          Expanded(
            child: Stack(
              children: [
                Row(
                  children: [
                    // Local files panel
                    Expanded(
                      child: _FileExplorerPane(
                        title: 'Local Machine',
                        subtitle:
                            sessionProvider.currentMachine?.username ?? '',
                        isLocal: true,
                      ),
                    ),
                    // Divider
                    Container(
                      width: 1,
                      color: colorScheme.outline.withValues(alpha: 0.2),
                    ),
                    // Remote files panel
                    Expanded(
                      child: _FileExplorerPane(
                        title: 'Remote Machine',
                        subtitle:
                            sessionProvider.destinationMachine?.username ?? '',
                        isLocal: false,
                      ),
                    ),
                  ],
                ),
                // Transfer status overlay
                Positioned(
                  right: AppSpacing.md,
                  bottom: AppSpacing.md,
                  child: const TransferStatusWidget(),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ToolbarButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onPressed;
  final bool isDestructive;

  const _ToolbarButton({
    required this.icon,
    required this.label,
    required this.onPressed,
    this.isDestructive = false,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final buttonColor = isDestructive ? colorScheme.error : colorScheme.primary;

    return OutlinedButton.icon(
      onPressed: onPressed,
      icon: Icon(icon, size: 18, color: buttonColor),
      label: Text(label, style: TextStyle(color: buttonColor)),
      style: OutlinedButton.styleFrom(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        side: BorderSide(
            color: isDestructive
                ? colorScheme.error.withValues(alpha: 0.5)
                : colorScheme.outline.withValues(alpha: 0.3)),
      ),
    );
  }
}

class _FileExplorerPane extends StatelessWidget {
  final String title;
  final String subtitle;
  final bool isLocal;

  const _FileExplorerPane({
    required this.title,
    required this.subtitle,
    required this.isLocal,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final fileSystemProvider = context.watch<FileSystemProvider>();

    final files = isLocal
        ? fileSystemProvider.localFiles
        : fileSystemProvider.remoteFiles;
    final currentPath = isLocal
        ? fileSystemProvider.localCurrentPath
        : fileSystemProvider.remoteCurrentPath;
    final isLoading = isLocal
        ? fileSystemProvider.isLoadingLocal
        : fileSystemProvider.isLoadingRemote;

    final selectedCount = isLocal
        ? fileSystemProvider.selectedLocalFiles.length
        : fileSystemProvider.selectedRemoteFiles.length;

    return DragDropZone(
      enabled: isLocal,
      onFilesDropped: (paths) {
        if (isLocal) {
          fileSystemProvider.addExternalFilesToLocal(paths);
          AppLogger.info('External files dropped: ${paths.length}');
        }
      },
      child: Column(
        children: [
          // Pane header
          Container(
            padding: AppSpacing.paddingMd,
            decoration: BoxDecoration(
              color: colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
              border: Border(
                bottom: BorderSide(
                  color: colorScheme.outline.withValues(alpha: 0.2),
                  width: 1,
                ),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      isLocal ? Icons.computer : Icons.cloud,
                      color: colorScheme.primary,
                      size: 20,
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            title,
                            style: context.textStyles.titleSmall?.semiBold,
                          ),
                          Text(
                            subtitle,
                            style: context.textStyles.bodySmall
                                ?.withColor(colorScheme.onSurfaceVariant),
                          ),
                        ],
                      ),
                    ),
                    if (selectedCount > 0)
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: AppSpacing.sm,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: colorScheme.primary,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(
                          '$selectedCount selected',
                          style: context.textStyles.bodySmall?.copyWith(
                            color: colorScheme.onPrimary,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    const SizedBox(width: AppSpacing.xs),
                    PopupMenuButton(
                      icon: Icon(Icons.more_vert,
                          size: 18, color: colorScheme.onSurface),
                      itemBuilder: (context) => [
                        PopupMenuItem(
                          child: const Row(
                            children: [
                              Icon(Icons.select_all, size: 18),
                              SizedBox(width: AppSpacing.sm),
                              Text('Select All'),
                            ],
                          ),
                          onTap: () {
                            if (isLocal) {
                              fileSystemProvider.selectAllLocal();
                            } else {
                              fileSystemProvider.selectAllRemote();
                            }
                          },
                        ),
                        PopupMenuItem(
                          child: const Row(
                            children: [
                              Icon(Icons.deselect, size: 18),
                              SizedBox(width: AppSpacing.sm),
                              Text('Clear Selection'),
                            ],
                          ),
                          onTap: () {
                            if (isLocal) {
                              fileSystemProvider.clearLocalSelection();
                            } else {
                              fileSystemProvider.clearRemoteSelection();
                            }
                          },
                        ),
                        PopupMenuItem(
                          child: const Row(
                            children: [
                              Icon(Icons.refresh, size: 18),
                              SizedBox(width: AppSpacing.sm),
                              Text('Refresh'),
                            ],
                          ),
                          onTap: () {
                            if (isLocal) {
                              fileSystemProvider.loadLocalFiles();
                            } else {
                              fileSystemProvider.loadRemoteFiles();
                            }
                          },
                        ),
                      ],
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.sm),
                // Navigation up button - hide when at root
                Row(
                  children: [
                    // Only show back button if not at root
                    if (!(isLocal
                            ? fileSystemProvider.isAtLocalRoot
                            : fileSystemProvider.isAtRemoteRoot) &&
                        currentPath != '/' &&
                        currentPath != '.')
                      IconButton(
                        icon: const Icon(Icons.arrow_back, size: 18),
                        onPressed: () {
                          if (isLocal) {
                            fileSystemProvider.navigateLocalUp();
                          } else {
                            fileSystemProvider.navigateRemoteUp();
                          }
                        },
                        padding: EdgeInsets.zero,
                        constraints: const BoxConstraints(),
                        color: colorScheme.primary,
                      ),
                    const SizedBox(width: AppSpacing.xs),
                    Expanded(
                      child: SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: _BreadcrumbPath(
                          path: currentPath,
                          isLocal: isLocal,
                          onSegmentTap: (path) {
                            if (isLocal) {
                              fileSystemProvider.loadLocalFiles(path);
                            } else {
                              fileSystemProvider.loadRemoteFiles(path);
                            }
                          },
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),

          // File list
          Expanded(
            child: isLoading
                ? const Center(child: CircularProgressIndicator())
                : files.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(
                              Icons.folder_open,
                              size: 64,
                              color: colorScheme.onSurfaceVariant,
                            ),
                            const SizedBox(height: AppSpacing.md),
                            Text(
                              'No files',
                              style: context.textStyles.titleMedium,
                            ),
                          ],
                        ),
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.all(AppSpacing.sm),
                        itemCount: files.length,
                        itemBuilder: (context, index) {
                          final file = files[index];
                          return Padding(
                            padding: const EdgeInsets.only(
                              bottom: AppSpacing.xs,
                            ),
                            child: FileItemCard(
                              file: file,
                              onTap: () {
                                if (isLocal) {
                                  fileSystemProvider
                                      .toggleLocalFileSelection(index);
                                } else {
                                  fileSystemProvider
                                      .toggleRemoteFileSelection(index);
                                }
                              },
                              onDoubleTap: file.isDirectory
                                  ? () {
                                      if (isLocal) {
                                        fileSystemProvider
                                            .loadLocalFiles(file.path);
                                      } else {
                                        fileSystemProvider
                                            .loadRemoteFiles(file.path);
                                      }
                                    }
                                  : null,
                            ),
                          )
                              .animate()
                              .fadeIn(
                                duration: 200.ms,
                                delay: (20 * index).ms,
                              )
                              .slideX(begin: 0.1, end: 0);
                        },
                      ),
          ),
        ],
      ),
    );
  }
}

/// Clickable breadcrumb path widget that displays path segments as clickable buttons
class _BreadcrumbPath extends StatelessWidget {
  final String path;
  final bool isLocal;
  final void Function(String path) onSegmentTap;

  const _BreadcrumbPath({
    required this.path,
    required this.isLocal,
    required this.onSegmentTap,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    // Split path into segments
    final normalizedPath = path.replaceAll('\\', '/');
    final segments =
        normalizedPath.split('/').where((s) => s.isNotEmpty).toList();

    // Handle root path
    final isAbsolute = normalizedPath.startsWith('/');

    if (segments.isEmpty) {
      return InkWell(
        onTap: () => onSegmentTap('/'),
        borderRadius: BorderRadius.circular(4),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
          child: Text(
            '/',
            style: context.textStyles.bodySmall?.copyWith(
              color: colorScheme.primary,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
      );
    }

    final List<Widget> widgets = [];

    // Add root if absolute path
    if (isAbsolute) {
      widgets.add(
        InkWell(
          onTap: () => onSegmentTap('/'),
          borderRadius: BorderRadius.circular(4),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
            child: Text(
              '/',
              style: context.textStyles.bodySmall?.copyWith(
                color: colorScheme.primary,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ),
      );
    }

    // Add each segment
    for (int i = 0; i < segments.length; i++) {
      final segment = segments[i];
      final isLast = i == segments.length - 1;

      // Build path up to this segment
      final pathToSegment = isAbsolute
          ? '/${segments.sublist(0, i + 1).join('/')}'
          : segments.sublist(0, i + 1).join('/');

      // Add separator if not first (and not after root)
      if (i > 0 || isAbsolute) {
        widgets.add(
          Icon(
            Icons.chevron_right,
            size: 16,
            color: colorScheme.onSurfaceVariant.withValues(alpha: 0.5),
          ),
        );
      }

      // Add segment button
      widgets.add(
        InkWell(
          onTap: isLast ? null : () => onSegmentTap(pathToSegment),
          borderRadius: BorderRadius.circular(4),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
            child: Text(
              segment,
              style: context.textStyles.bodySmall?.copyWith(
                color:
                    isLast ? colorScheme.onSurfaceVariant : colorScheme.primary,
                fontWeight: isLast ? FontWeight.w500 : FontWeight.normal,
              ),
            ),
          ),
        ),
      );
    }

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: widgets,
    );
  }
}
