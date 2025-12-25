import 'package:lanfxplorer/presentation/screens/landing_page.dart';
import 'package:lanfxplorer/presentation/screens/login_page.dart';
import 'package:lanfxplorer/presentation/screens/main_page.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// GoRouter configuration for app navigation
///
/// This uses go_router for declarative routing, which provides:
/// - Type-safe navigation
/// - Deep linking support (web URLs, app links)
/// - Easy route parameters
/// - Navigation guards and redirects
///
/// To add a new route:
/// 1. Add a route constant to AppRoutes below
/// 2. Add a GoRoute to the routes list
/// 3. Navigate using context.go() or context.push()
/// 4. Use context.pop() to go back.
class AppRouter {
  static final GoRouter router = GoRouter(
    initialLocation: AppRoutes.login,
    routes: [
      GoRoute(
        path: AppRoutes.login,
        name: 'login',
        pageBuilder: (context, state) => CustomTransitionPage(
          child: const LoginPage(),
          transitionsBuilder: (context, animation, secondaryAnimation, child) {
            return FadeTransition(opacity: animation, child: child);
          },
        ),
      ),
      GoRoute(
        path: AppRoutes.home,
        name: 'home',
        pageBuilder: (context, state) => CustomTransitionPage(
          child: const LandingPage(),
          transitionsBuilder: (context, animation, secondaryAnimation, child) {
            return FadeTransition(opacity: animation, child: child);
          },
        ),
      ),
      GoRoute(
        path: AppRoutes.main,
        name: 'main',
        pageBuilder: (context, state) => CustomTransitionPage(
          child: const MainPage(),
          transitionsBuilder: (context, animation, secondaryAnimation, child) {
            return SlideTransition(
              position: Tween<Offset>(
                begin: const Offset(1, 0),
                end: Offset.zero,
              ).animate(CurvedAnimation(
                parent: animation,
                curve: Curves.easeInOut,
              )),
              child: child,
            );
          },
        ),
      ),
    ],
  );
}

/// Route path constants
/// Use these instead of hard-coding route strings
class AppRoutes {
  static const String login = '/';
  static const String home = '/home';
  static const String main = '/main';
}
