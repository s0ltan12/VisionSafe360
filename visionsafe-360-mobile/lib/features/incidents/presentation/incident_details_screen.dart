import 'package:flutter/material.dart';

import '../../../core/constants/quick_actions.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/utils/app_screen.dart';
import '../../../shared/models/safety_alert.dart';
import '../../../shared/providers/app_providers.dart';
import '../../../shared/widgets/app_widgets.dart';
import 'incident_widgets.dart';

class IncidentDetailsScreen extends StatelessWidget {
  const IncidentDetailsScreen({
    super.key,
    required this.theme,
    required this.copy,
    required this.isDark,
    required this.isRtl,
    required this.activeTab,
    required this.onNavigate,
  });

  final AppTheme theme;
  final Map<String, String> copy;
  final bool isDark;
  final bool isRtl;
  final AppTab activeTab;
  final ValueChanged<AppScreen> onNavigate;

  @override
  Widget build(BuildContext context) {
    final incidents = context.incidentProvider;
    final alert = incidents.selectedAlert;
    if (alert == null) return const SizedBox.shrink();

    return Column(
      children: [
        Container(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
          decoration: BoxDecoration(
            color: theme.bg.withOpacity(.92),
            border: Border(bottom: BorderSide(color: theme.border)),
          ),
          child: Row(
            children: [
              _squareButton(
                isRtl ? Icons.chevron_right : Icons.arrow_back,
                () => onNavigate(
                  activeTab == AppTab.history ? AppScreen.history : AppScreen.dashboard,
                ),
              ),
              Expanded(
                child: Text(
                  'Incident # ${alert.id}',
                  textAlign: TextAlign.center,
                  style: labelStyle(theme.muted, 10),
                ),
              ),
              _squareButton(Icons.phone_outlined, () {}, color: AppColors.orange),
            ],
          ),
        ),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.only(bottom: 132),
            children: [
              Stack(
                children: [
                  AspectRatio(
                    aspectRatio: 16 / 9,
                    child: Container(
                      color: const Color(0xFF050505),
                      child: Image.network(alert.snapshot, fit: BoxFit.contain),
                    ),
                  ),
                  Positioned(
                    top: 14,
                    left: isRtl ? null : 14,
                    right: isRtl ? 14 : null,
                    child: severityBadge(alert.severity),
                  ),
                ],
              ),
              Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(child: Text(alert.type, style: titleStyle(theme, 24))),
                        statusBadge(alert.status),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 18,
                      runSpacing: 8,
                      children: [
                        inlineMeta(Icons.location_on_outlined, alert.location, theme),
                        inlineMeta(Icons.schedule, alert.timestamp, theme),
                      ],
                    ),
                    const SizedBox(height: 26),
                    _timelinePanel(alert),
                    const SizedBox(height: 16),
                    _reportPanel(alert),
                    const SizedBox(height: 20),
                    _actionArea(context, alert),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget resolveSheet(BuildContext context) {
    final incidents = context.incidentProvider;
    final auth = context.authProvider;
    final alert = incidents.selectedAlert;
    if (alert == null) return const SizedBox.shrink();

    return Positioned.fill(
      child: Container(
        color: Colors.black.withOpacity(.78),
        alignment: Alignment.bottomCenter,
        padding: const EdgeInsets.all(16),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: theme.surface,
            borderRadius: BorderRadius.circular(30),
            border: Border.all(color: theme.border),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: Text(copy['recordAction']!, style: titleStyle(theme, 18))),
                  IconButton(
                    onPressed: incidents.hideResolveSheet,
                    icon: Icon(Icons.close, color: theme.muted),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              ...quickActions.map(
                (action) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Material(
                    color: isDark ? const Color(0xFF202020) : const Color(0xFFF8FAFC),
                    borderRadius: BorderRadius.circular(16),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(16),
                      onTap: () {
                        incidents.resolve(
                          id: alert.id,
                          action: action,
                          timestamp: TimeOfDay.now().format(context),
                          userName: auth.user?.name ?? 'Eng. Ahmed',
                        );
                      },
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
                        child: Row(
                          children: [
                            Expanded(child: Text(action, style: itemTitleStyle(theme, 12))),
                            const Icon(Icons.chevron_right, color: AppColors.orange),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _timelinePanel(SafetyAlert alert) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: panelDecoration(theme, isDark),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(copy['auditTimeline']!, style: labelStyle(theme.muted, 10)),
          const SizedBox(height: 16),
          ...alert.timeline.map((event) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 15,
                    height: 15,
                    margin: const EdgeInsets.only(top: 2),
                    decoration: BoxDecoration(
                      color: statusColor(event.status),
                      shape: BoxShape.circle,
                      border: Border.all(color: theme.bg, width: 2),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Text(statusText(event.status),
                                  style: itemTitleStyle(theme, 10)),
                            ),
                            Text(
                              event.timestamp,
                              style: TextStyle(
                                color: theme.muted,
                                fontSize: 9,
                                fontWeight: FontWeight.w700,
                                letterSpacing: .6,
                              ),
                            ),
                          ],
                        ),
                        if (event.user != null)
                          Padding(
                            padding: const EdgeInsets.only(top: 3),
                            child: Text('By ${event.user}',
                                style: labelStyle(AppColors.orange, 9)),
                          ),
                        if (event.note != null)
                          Padding(
                            padding: const EdgeInsets.only(top: 5),
                            child: Text(
                              '"${event.note}"',
                              style: TextStyle(
                                color: theme.body,
                                fontSize: 12,
                                fontStyle: FontStyle.italic,
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }

  Widget _reportPanel(SafetyAlert alert) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: panelDecoration(theme, isDark),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.assignment_outlined, color: AppColors.orange, size: 22),
              const SizedBox(width: 9),
              Text(copy['incidentReport']!, style: labelStyle(theme.muted, 11)),
            ],
          ),
          const SizedBox(height: 14),
          Text(
            alert.description,
            style: TextStyle(
              color: theme.body,
              fontSize: 14,
              height: 1.45,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Widget _actionArea(BuildContext context, SafetyAlert alert) {
    final incidents = context.incidentProvider;
    final auth = context.authProvider;

    if (alert.status == AlertStatus.fresh) {
      return primaryButton(
        copy['acknowledge']!,
        () {
          incidents.acknowledge(
            id: alert.id,
            timestamp: TimeOfDay.now().format(context),
            userName: auth.user?.name ?? 'Eng. Ahmed',
          );
        },
        icon: Icons.shield_outlined,
      );
    }
    if (alert.status == AlertStatus.acknowledged) {
      return primaryButton(
        copy['resolve']!,
        incidents.showResolveSheet,
        icon: Icons.check_circle_outline,
        color: AppColors.success,
        foreground: Colors.white,
      );
    }
    return Container(
      height: 62,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: AppColors.success.withOpacity(.12),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: AppColors.success.withOpacity(.35)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.check, color: AppColors.success),
          const SizedBox(width: 10),
          Text(copy['caseClosed']!, style: labelStyle(AppColors.success, 11)),
        ],
      ),
    );
  }

  Widget _squareButton(IconData icon, VoidCallback onTap, {Color? color}) {
    return IconButton(
      onPressed: onTap,
      icon: Icon(icon, color: color ?? theme.text),
      style: IconButton.styleFrom(
        backgroundColor: theme.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    );
  }
}
