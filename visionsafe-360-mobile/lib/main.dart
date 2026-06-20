import 'package:flutter/material.dart';

import 'core/network/api_client.dart';
import 'core/network/token_storage.dart';
import 'core/theme/app_theme.dart';
import 'features/auth/data/auth_repository.dart';
import 'features/auth/domain/auth_provider.dart';
import 'features/incidents/data/incident_repository.dart';
import 'features/incidents/domain/incident_provider.dart';
import 'features/settings/data/settings_repository.dart';
import 'features/settings/domain/settings_provider.dart';
import 'shared/providers/app_providers.dart';
import 'shared/widgets/app_shell.dart';

void main() {
  final tokenStorage = TokenStorage();
  final apiClient = ApiClient(tokenStorage: tokenStorage);

  runApp(
    AppProviderScope(
      authProvider: AuthProvider(
        AuthRepository(apiClient: apiClient, tokenStorage: tokenStorage),
      ),
      incidentProvider: IncidentProvider(IncidentRepository(apiClient: apiClient)),
      settingsProvider: SettingsProvider(SettingsRepository()),
      builder: (_) => const VisionSafeApp(),
    ),
  );
}

class VisionSafeApp extends StatelessWidget {
  const VisionSafeApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'VisionSafe 360',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        fontFamily: 'Roboto',
        colorSchemeSeed: AppColors.orange,
      ),
      home: const VisionSafeHome(),
    );
  }
}
