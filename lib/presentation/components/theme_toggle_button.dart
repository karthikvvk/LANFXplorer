import 'package:files/presentation/providers/theme_provider.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

class ThemeToggleButton extends StatelessWidget {
  const ThemeToggleButton({super.key});

  @override
  Widget build(BuildContext context) {
    final themeProvider = context.watch<ThemeProvider>();
    final isDark = themeProvider.isDarkMode;

    return IconButton(
      icon: AnimatedSwitcher(
        duration: const Duration(milliseconds: 300),
        transitionBuilder: (child, animation) => RotationTransition(
          turns: animation,
          child: child,
        ),
        child: Icon(
          isDark ? Icons.light_mode : Icons.dark_mode,
          key: ValueKey(isDark),
          color: Theme.of(context).colorScheme.onSurface,
        ),
      ),
      onPressed: themeProvider.toggleTheme,
      tooltip: isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode',
    );
  }
}
