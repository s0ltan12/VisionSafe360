import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/utils/app_screen.dart';
import '../../../shared/models/safety_alert.dart';
import '../../../shared/providers/app_providers.dart';
import '../../../shared/widgets/app_widgets.dart';
import '../../incidents/presentation/incident_widgets.dart';

class HistoryScreen extends StatelessWidget {
  const HistoryScreen({
    super.key,
    required this.theme,
    required this.copy,
    required this.isDark,
    required this.isRtl,
    required this.onNavigate,
  });

  final AppTheme theme;
  final Map<String, String> copy;
  final bool isDark;
  final bool isRtl;
  final ValueChanged<AppScreen> onNavigate;

  @override
  Widget build(BuildContext context) {
    final incidents = context.incidentProvider;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 28, 24, 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(copy['logHistory']!, style: titleStyle(theme, 24)),
              const SizedBox(height: 16),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: [
                    _filterChip(context, 'All', incidents.historyFilter == null, null),
                    _filterChip(
                      context,
                      'Critical',
                      incidents.historyFilter == Severity.critical,
                      Severity.critical,
                    ),
                    _filterChip(
                      context,
                      'Medium',
                      incidents.historyFilter == Severity.medium,
                      Severity.medium,
                    ),
                    _filterChip(
                      context,
                      'Low',
                      incidents.historyFilter == Severity.low,
                      Severity.low,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(24, 4, 24, 132),
            children: incidents.filteredHistory.map((alert) {
              return IncidentTile(
                alert: alert,
                theme: theme,
                isDark: isDark,
                isRtl: isRtl,
                onTap: () {
                  incidents.selectAlert(alert);
                  onNavigate(AppScreen.details);
                },
              );
            }).toList(),
          ),
        ),
      ],
    );
  }

  Widget _filterChip(
    BuildContext context,
    String label,
    bool active,
    Severity? severity,
  ) {
    return Padding(
      padding: const EdgeInsetsDirectional.only(end: 8),
      child: ChoiceChip(
        label: Text(label),
        selected: active,
        onSelected: (_) => context.incidentProvider.setHistoryFilter(severity),
        selectedColor: AppColors.orange,
        backgroundColor: theme.surface,
        side: BorderSide(color: active ? AppColors.orange : theme.border),
        labelStyle: labelStyle(active ? const Color(0xFF101010) : theme.muted, 10),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }
}
