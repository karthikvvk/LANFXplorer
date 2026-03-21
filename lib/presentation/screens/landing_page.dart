import 'package:lanfxplorer/data/models/machine.dart';
import 'package:lanfxplorer/presentation/components/machine_card.dart';
import 'package:lanfxplorer/presentation/components/theme_toggle_button.dart';
import 'package:lanfxplorer/presentation/dialogs/connection_dialog.dart';
import 'package:lanfxplorer/presentation/dialogs/troubleshoot_dialog.dart';
import 'package:lanfxplorer/presentation/providers/env_provider.dart';
import 'package:lanfxplorer/presentation/providers/network_provider.dart';
import 'package:lanfxplorer/presentation/providers/session_provider.dart';
import 'package:lanfxplorer/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

class LandingPage extends StatefulWidget {
  const LandingPage({super.key});

  @override
  State<LandingPage> createState() => _LandingPageState();
}

class _LandingPageState extends State<LandingPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await context.read<EnvProvider>().load();
      _initializeCurrentMachine();
      _scanNetwork();
    });
  }

  void _initializeCurrentMachine() {
    final env = context.read<EnvProvider>().env;
    if (env == null) return;

    context.read<SessionProvider>().setCurrentMachine(
          Machine(
            id: 'current',
            username: env.user,
            ipAddress: env.host,
            os: env.system,
          ),
        );
  }

  void _scanNetwork() {
    context.read<NetworkProvider>().scanNetwork();
  }

  void _onMachineSelected(Machine machine) async {
    // Show connection dialog for password authentication
    final result = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (context) => ConnectionDialog(
        machine: machine,
        apiService: context.read<NetworkProvider>().apiService,
      ),
    );

    // If handshake successful, proceed with session
    if (result == true && mounted) {
      context.read<EnvProvider>().updateDestHost(machine.ipAddress);
      context.read<SessionProvider>().startSession(machine);
      context.push('/main');
    }
  }

  void _logout() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Sign Out'),
        content: const Text(
            'Are you sure you want to sign out? You will need to enter your credentials again.'),
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

  void _showTroubleshoot() {
    showDialog(
      context: context,
      builder: (context) => TroubleshootDialog(
        apiService: context.read<NetworkProvider>().apiService,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final sessionProvider = context.watch<SessionProvider>();
    final networkProvider = context.watch<NetworkProvider>();

    return Scaffold(
      body: Column(
        children: [
          // Header with current machine details
          Container(
            padding: AppSpacing.paddingMd,
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
                Icon(Icons.computer, color: colorScheme.primary, size: 32),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Current Machine',
                        style: context.textStyles.labelSmall
                            ?.withColor(colorScheme.onSurfaceVariant),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        sessionProvider.currentMachine?.username ??
                            'Loading...',
                        style: context.textStyles.titleMedium?.semiBold,
                      ),
                      Text(
                        sessionProvider.currentMachine?.ipAddress ?? '',
                        style: context.textStyles.bodySmall
                            ?.withColor(colorScheme.onSurfaceVariant),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.build),
                  onPressed: _showTroubleshoot,
                  tooltip: 'Troubleshoot',
                  color: colorScheme.tertiary,
                ),
                IconButton(
                  icon: const Icon(Icons.refresh),
                  onPressed: networkProvider.isScanning ? null : _scanNetwork,
                  tooltip: 'Refresh Network Scan',
                  color: colorScheme.primary,
                ),
                IconButton(
                  icon: const Icon(Icons.logout),
                  onPressed: _logout,
                  tooltip: 'Sign Out',
                  color: colorScheme.error,
                ),
                const ThemeToggleButton(),
              ],
            ),
          ),

          // Main content area with grid of neighboring machines
          Expanded(
            child: networkProvider.isScanning
                ? _buildLoadingState()
                : networkProvider.availableMachines.isEmpty
                    ? _buildEmptyState()
                    : _buildMachineGrid(networkProvider.availableMachines),
          ),
        ],
      ),
    );
  }

  Widget _buildLoadingState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const CircularProgressIndicator(),
          const SizedBox(height: AppSpacing.lg),
          Text(
            'Scanning for devices...',
            style: context.textStyles.titleMedium,
          ),
        ],
      )
          .animate(onPlay: (controller) => controller.repeat())
          .fadeIn(duration: 800.ms)
          .then()
          .fadeOut(duration: 800.ms),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.devices_other,
            size: 64,
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
          const SizedBox(height: AppSpacing.lg),
          // "No devices found" label + inline Troubleshoot button
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'No devices found',
                style: context.textStyles.titleLarge,
              ),
              const SizedBox(width: 8),
              TextButton.icon(
                onPressed: _showTroubleshoot,
                icon: const Icon(Icons.build, size: 16),
                label: const Text('Troubleshoot'),
                style: TextButton.styleFrom(
                  foregroundColor:
                      Theme.of(context).colorScheme.onSurfaceVariant,
                  textStyle: context.textStyles.bodySmall,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            'Make sure other devices are connected to the same network',
            style: context.textStyles.bodyMedium?.withColor(
              Theme.of(context).colorScheme.onSurfaceVariant,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: AppSpacing.lg),
          OutlinedButton.icon(
            onPressed: _scanNetwork,
            icon: const Icon(Icons.refresh),
            label: const Text('Scan Again'),
          ),
        ],
      ).animate().fadeIn(duration: 500.ms).slideY(begin: 0.2, end: 0),
    );
  }

  Widget _buildMachineGrid(List<Machine> machines) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // Responsive columns based on width
        int columns = 2;
        if (constraints.maxWidth > 600) columns = 3;
        if (constraints.maxWidth > 900) columns = 4;
        if (constraints.maxWidth > 1200) columns = 5;

        return GridView.builder(
          padding: AppSpacing.paddingLg,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            crossAxisSpacing: AppSpacing.md,
            mainAxisSpacing: AppSpacing.md,
            childAspectRatio: 1.1,
          ),
          itemCount: machines.length,
          itemBuilder: (context, index) {
            return MachineCard(
              machine: machines[index],
              onTap: () => _onMachineSelected(machines[index]),
            )
                .animate()
                .fadeIn(
                  duration: 300.ms,
                  delay: (50 * index).ms,
                )
                .slideY(begin: 0.2, end: 0);
          },
        );
      },
    );
  }
}
