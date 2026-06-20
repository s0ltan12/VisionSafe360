import 'package:flutter/widgets.dart';

import '../../features/auth/domain/auth_provider.dart';
import '../../features/incidents/domain/incident_provider.dart';
import '../../features/settings/domain/settings_provider.dart';

class AppProviders extends StatelessWidget {
  const AppProviders({
    super.key,
    required this.authProvider,
    required this.incidentProvider,
    required this.settingsProvider,
    required this.child,
  });

  final AuthProvider authProvider;
  final IncidentProvider incidentProvider;
  final SettingsProvider settingsProvider;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return AppInheritedNotifier<AuthProvider>(
      notifier: authProvider,
      child: AppInheritedNotifier<IncidentProvider>(
        notifier: incidentProvider,
        child: AppInheritedNotifier<SettingsProvider>(
          notifier: settingsProvider,
          child: child,
        ),
      ),
    );
  }
}

class AppInheritedNotifier<T extends Listenable> extends InheritedNotifier<T> {
  const AppInheritedNotifier({
    super.key,
    required super.notifier,
    required super.child,
  });
}

class AppProviderScope extends StatefulWidget {
  const AppProviderScope({
    super.key,
    required this.authProvider,
    required this.incidentProvider,
    required this.settingsProvider,
    required this.builder,
  });

  final AuthProvider authProvider;
  final IncidentProvider incidentProvider;
  final SettingsProvider settingsProvider;
  final WidgetBuilder builder;

  @override
  State<AppProviderScope> createState() => _AppProviderScopeState();
}

class _AppProviderScopeState extends State<AppProviderScope> {
  @override
  void dispose() {
    widget.authProvider.dispose();
    widget.incidentProvider.dispose();
    widget.settingsProvider.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AppProviders(
      authProvider: widget.authProvider,
      incidentProvider: widget.incidentProvider,
      settingsProvider: widget.settingsProvider,
      child: Builder(builder: widget.builder),
    );
  }
}

extension ProviderLookup on BuildContext {
  AuthProvider get authProvider {
    final provider =
        dependOnInheritedWidgetOfExactType<AppInheritedNotifier<AuthProvider>>();
    assert(provider?.notifier != null, 'AuthProvider not found in widget tree.');
    return provider!.notifier!;
  }

  IncidentProvider get incidentProvider {
    final provider =
        dependOnInheritedWidgetOfExactType<AppInheritedNotifier<IncidentProvider>>();
    assert(provider?.notifier != null, 'IncidentProvider not found in widget tree.');
    return provider!.notifier!;
  }

  SettingsProvider get settingsProvider {
    final provider =
        dependOnInheritedWidgetOfExactType<AppInheritedNotifier<SettingsProvider>>();
    assert(provider?.notifier != null, 'SettingsProvider not found in widget tree.');
    return provider!.notifier!;
  }
}
