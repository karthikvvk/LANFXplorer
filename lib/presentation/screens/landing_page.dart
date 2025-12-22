import 'package:files/data/models/machine.dart';
import 'package:files/presentation/components/machine_card.dart';
import 'package:files/presentation/components/theme_toggle_button.dart';
import 'package:files/presentation/dialogs/connection_dialog.dart';
import 'package:files/presentation/providers/env_provider.dart';
import 'package:files/presentation/providers/network_provider.dart';
import 'package:files/presentation/providers/session_provider.dart';
import 'package:files/theme.dart';
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
                  icon: const Icon(Icons.refresh),
                  onPressed: networkProvider.isScanning ? null : _scanNetwork,
                  tooltip: 'Refresh Network Scan',
                  color: colorScheme.primary,
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
          Text(
            'No devices found',
            style: context.textStyles.titleLarge,
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
