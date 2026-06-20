import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../shared/providers/app_providers.dart';
import '../../../shared/widgets/app_widgets.dart';
import '../../incidents/presentation/incident_widgets.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({
    super.key,
    required this.theme,
    required this.copy,
    required this.isDark,
    required this.isRtl,
    required this.onLogout,
  });

  final AppTheme theme;
  final Map<String, String> copy;
  final bool isDark;
  final bool isRtl;
  final VoidCallback onLogout;

  @override
  Widget build(BuildContext context) {
    final auth = context.authProvider;
    final settings = context.settingsProvider;
    final user = auth.user;

    return ListView(
      padding: const EdgeInsets.fromLTRB(28, 30, 28, 132),
      children: [
        Text(copy['settings']!, style: titleStyle(theme, 24)),
        const SizedBox(height: 28),
        Container(
          padding: const EdgeInsets.all(20),
          decoration: panelDecoration(theme, isDark),
          child: Row(
            children: [
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  color: AppColors.orange.withOpacity(.1),
                  shape: BoxShape.circle,
                  border: Border.all(color: AppColors.orange.withOpacity(.22)),
                ),
                child: const Icon(Icons.person_outline, color: AppColors.orange, size: 34),
              ),
              const SizedBox(width: 18),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(user?.name ?? 'Eng. Ahmed', style: titleStyle(theme, 18)),
                    const SizedBox(height: 4),
                    Text(
                      user?.role ?? 'HSE Site Supervisor',
                      style: labelStyle(AppColors.orange, 10),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 28),
        Text(copy['account']!, style: labelStyle(theme.muted, 10)),
        const SizedBox(height: 12),
        Container(
          decoration: panelDecoration(theme, isDark),
          clipBehavior: Clip.antiAlias,
          child: Column(
            children: [
              _settingsRow(
                icon: Icons.language,
                iconColor: const Color(0xFF2563EB),
                title: copy['language']!,
                trailing: copy['changeLang']!,
                onTap: settings.toggleLanguage,
              ),
              Divider(height: 1, color: theme.border),
              _settingsRow(
                icon: isDark ? Icons.dark_mode_outlined : Icons.light_mode_outlined,
                iconColor: AppColors.orange,
                title: copy['theme']!,
                trailing: isDark ? copy['lightMode']! : copy['darkMode']!,
                onTap: settings.toggleTheme,
              ),
              Divider(height: 1, color: theme.border),
              _settingsRow(
                icon: Icons.logout,
                iconColor: AppColors.danger,
                title: copy['logout']!,
                trailing: '',
                danger: true,
                onTap: () async {
                  await auth.logout();
                  onLogout();
                },
              ),
            ],
          ),
        ),
        const SizedBox(height: 46),
        Center(child: Text(copy['appVer']!, style: labelStyle(theme.muted, 10))),
      ],
    );
  }

  Widget _settingsRow({
    required IconData icon,
    required Color iconColor,
    required String title,
    required String trailing,
    required VoidCallback onTap,
    bool danger = false,
  }) {
    final color = danger ? AppColors.danger : theme.text;
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(9),
              decoration: BoxDecoration(
                color: iconColor.withOpacity(.11),
                borderRadius: BorderRadius.circular(13),
              ),
              child: Icon(icon, color: iconColor, size: 21),
            ),
            const SizedBox(width: 14),
            Expanded(child: Text(title, style: labelStyle(color, 12))),
            if (trailing.isNotEmpty)
              Flexible(
                child: Text(
                  trailing,
                  textAlign: TextAlign.end,
                  overflow: TextOverflow.ellipsis,
                  style: labelStyle(AppColors.orange, 10),
                ),
              ),
            Icon(
              isRtl ? Icons.chevron_left : Icons.chevron_right,
              color: danger ? AppColors.danger.withOpacity(.5) : theme.muted,
            ),
          ],
        ),
      ),
    );
  }
}
