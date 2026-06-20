import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/utils/app_screen.dart';
import '../../features/auth/presentation/login_screen.dart';
import '../../features/history/presentation/history_screen.dart';
import '../../features/incidents/presentation/dashboard_screen.dart';
import '../../features/incidents/presentation/incident_details_screen.dart';
import '../../features/incidents/presentation/loading_screen.dart';
import '../../features/settings/presentation/settings_screen.dart';
import '../providers/app_providers.dart';

class VisionSafeHome extends StatefulWidget {
  const VisionSafeHome({super.key});

  @override
  State<VisionSafeHome> createState() => _VisionSafeHomeState();
}

class _VisionSafeHomeState extends State<VisionSafeHome> {
  AppScreen currentScreen = AppScreen.loading;
  AppTab activeTab = AppTab.home;
  int loadingProgress = 0;
  Timer? loadingTimer;

  @override
  void initState() {
    super.initState();
    _startLoading();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.authProvider.restoreSession();
    });
  }

  @override
  void dispose() {
    loadingTimer?.cancel();
    super.dispose();
  }

  void _startLoading() {
    loadingTimer = Timer.periodic(const Duration(milliseconds: 50), (timer) {
      if (!mounted) return;
      setState(() => loadingProgress = math.min(100, loadingProgress + 2));
      if (loadingProgress >= 100) {
        timer.cancel();
        Future.delayed(const Duration(milliseconds: 450), () {
          if (mounted) setState(() => currentScreen = AppScreen.login);
        });
      }
    });
  }

  void _goTo(AppScreen screen) {
    setState(() => currentScreen = screen);
  }

  void _setTab(AppTab tab, AppScreen screen) {
    setState(() {
      activeTab = tab;
      currentScreen = screen;
    });
    if (screen == AppScreen.history) {
      context.incidentProvider.loadHistory();
    }
  }

  void _handleLoggedIn() {
    setState(() {
      currentScreen = AppScreen.dashboard;
      activeTab = AppTab.home;
    });
    context.incidentProvider.loadIncidents();
    context.incidentProvider.scheduleNotification(
      shouldShow: () => mounted && currentScreen == AppScreen.dashboard,
    );
  }

  void _handleLogout() {
    context.incidentProvider.resetSessionUi();
    setState(() {
      currentScreen = AppScreen.login;
      activeTab = AppTab.home;
    });
  }

  @override
  Widget build(BuildContext context) {
    final settings = context.settingsProvider;
    final incidents = context.incidentProvider;
    final theme = AppTheme(settings.isDark);
    final copy = settings.copy;
    final detailScreen = IncidentDetailsScreen(
      theme: theme,
      copy: copy,
      isDark: settings.isDark,
      isRtl: settings.isRtl,
      activeTab: activeTab,
      onNavigate: _goTo,
    );

    return Directionality(
      textDirection: settings.isRtl ? TextDirection.rtl : TextDirection.ltr,
      child: Scaffold(
        backgroundColor: theme.bg,
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 430),
            child: Stack(
              children: [
                AnimatedContainer(
                  duration: const Duration(milliseconds: 250),
                  color: theme.bg,
                  child: SafeArea(
                    bottom: false,
                    child: switch (currentScreen) {
                      AppScreen.loading => LoadingScreen(
                          theme: theme,
                          copy: copy,
                          loadingProgress: loadingProgress,
                          isDark: settings.isDark,
                        ),
                      AppScreen.login => LoginScreen(
                          theme: theme,
                          copy: copy,
                          onLoggedIn: _handleLoggedIn,
                        ),
                      AppScreen.dashboard => DashboardScreen(
                          theme: theme,
                          copy: copy,
                          isDark: settings.isDark,
                          isRtl: settings.isRtl,
                          onNavigate: _goTo,
                        ),
                      AppScreen.history => HistoryScreen(
                          theme: theme,
                          copy: copy,
                          isDark: settings.isDark,
                          isRtl: settings.isRtl,
                          onNavigate: _goTo,
                        ),
                      AppScreen.details => detailScreen,
                      AppScreen.settings => SettingsScreen(
                          theme: theme,
                          copy: copy,
                          isDark: settings.isDark,
                          isRtl: settings.isRtl,
                          onLogout: _handleLogout,
                        ),
                    },
                  ),
                ),
                if (incidents.showNotification)
                  _NotificationBanner(
                    theme: theme,
                    copy: copy,
                    isRtl: settings.isRtl,
                    onOpen: () {
                      incidents.selectAlert(incidents.alerts.first);
                      _goTo(AppScreen.details);
                    },
                  ),
                if (currentScreen != AppScreen.login &&
                    currentScreen != AppScreen.loading)
                  _BottomNavigation(
                    theme: theme,
                    copy: copy,
                    activeTab: activeTab,
                    onTab: _setTab,
                  ),
                if (incidents.showResolveSheet) detailScreen.resolveSheet(context),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _NotificationBanner extends StatelessWidget {
  const _NotificationBanner({
    required this.theme,
    required this.copy,
    required this.isRtl,
    required this.onOpen,
  });

  final AppTheme theme;
  final Map<String, String> copy;
  final bool isRtl;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final incidents = context.incidentProvider;

    return Positioned(
      top: 46,
      left: 16,
      right: 16,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(26),
          onTap: onOpen,
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: theme.surface,
              borderRadius: BorderRadius.circular(26),
              border: Border.all(color: AppColors.danger, width: 2),
              boxShadow: [
                BoxShadow(
                  color: AppColors.danger.withOpacity(.25),
                  blurRadius: 28,
                  offset: const Offset(0, 14),
                ),
              ],
            ),
            child: Row(
              children: [
                Container(
                  width: 52,
                  height: 52,
                  decoration: BoxDecoration(
                    color: AppColors.danger.withOpacity(.13),
                    borderRadius: BorderRadius.circular(18),
                  ),
                  child: const Icon(
                    Icons.warning_amber_rounded,
                    color: AppColors.danger,
                    size: 32,
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(copy['criticalAlert']!, style: labelStyle(AppColors.danger, 10)),
                      const SizedBox(height: 4),
                      Text(
                        isRtl ? 'تم رصد سقوط: المنطقة ب' : 'Fall Detected: Sector B',
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: theme.text,
                          fontSize: 14,
                          fontWeight: FontWeight.w900,
                          letterSpacing: .2,
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  onPressed: incidents.hideNotification,
                  icon: Icon(Icons.close, color: theme.muted),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _BottomNavigation extends StatelessWidget {
  const _BottomNavigation({
    required this.theme,
    required this.copy,
    required this.activeTab,
    required this.onTab,
  });

  final AppTheme theme;
  final Map<String, String> copy;
  final AppTab activeTab;
  final void Function(AppTab tab, AppScreen screen) onTab;

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: 0,
      right: 0,
      bottom: 0,
      child: Container(
        height: 98,
        padding: const EdgeInsets.only(bottom: 22),
        decoration: BoxDecoration(
          color: theme.nav,
          border: Border(top: BorderSide(color: theme.border)),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            _navButton(
              Icons.home_outlined,
              copy['home']!,
              AppTab.home,
              () => onTab(AppTab.home, AppScreen.dashboard),
            ),
            _navButton(
              Icons.history,
              copy['history']!,
              AppTab.history,
              () => onTab(AppTab.history, AppScreen.history),
            ),
            _navButton(
              Icons.settings_outlined,
              copy['settings']!,
              AppTab.settings,
              () => onTab(AppTab.settings, AppScreen.settings),
            ),
          ],
        ),
      ),
    );
  }

  Widget _navButton(IconData icon, String label, AppTab tab, VoidCallback onTap) {
    final active = activeTab == tab;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(18),
      child: SizedBox(
        width: 92,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: active ? AppColors.orange.withOpacity(.12) : Colors.transparent,
                borderRadius: BorderRadius.circular(15),
              ),
              child: Icon(icon, color: active ? AppColors.orange : theme.muted, size: 26),
            ),
            const SizedBox(height: 3),
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: labelStyle(active ? AppColors.orange : theme.muted, 9),
            ),
          ],
        ),
      ),
    );
  }
}
