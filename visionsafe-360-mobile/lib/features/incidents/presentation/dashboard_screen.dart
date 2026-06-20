import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/utils/app_screen.dart';
import '../../../shared/providers/app_providers.dart';
import '../../../shared/widgets/app_widgets.dart';
import 'incident_widgets.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({
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
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  bool _requestedInitialLoad = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_requestedInitialLoad) {
      _requestedInitialLoad = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) context.incidentProvider.loadIncidents();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.authProvider;
    final incidents = context.incidentProvider;
    final activeCount = incidents.activeAlerts.length;

    return ListView(
      padding: const EdgeInsets.fromLTRB(24, 26, 24, 132),
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(widget.copy['authAs']!, style: labelStyle(widget.theme.muted, 10)),
                  const SizedBox(height: 4),
                  Text(auth.user?.name ?? 'Eng. Ahmed',
                      style: titleStyle(widget.theme, 24)),
                ],
              ),
            ),
            Stack(
              clipBehavior: Clip.none,
              children: [
                _iconBox(Icons.notifications_none),
                if (activeCount > 0)
                  Positioned(
                    top: 9,
                    right: 9,
                    child: Container(
                      width: 11,
                      height: 11,
                      decoration: BoxDecoration(
                        color: AppColors.danger,
                        shape: BoxShape.circle,
                        border: Border.all(color: widget.theme.surface, width: 2),
                      ),
                    ),
                  ),
              ],
            ),
          ],
        ),
        const SizedBox(height: 30),
        _insightPanel(),
        const SizedBox(height: 30),
        Text('${widget.copy['activeIncidents']} ($activeCount)',
            style: labelStyle(widget.theme.muted, 11)),
        const SizedBox(height: 14),
        ...incidents.activeAlerts.map(
          (alert) => IncidentTile(
            alert: alert,
            theme: widget.theme,
            isDark: widget.isDark,
            isRtl: widget.isRtl,
            large: true,
            onTap: () {
              incidents.selectAlert(alert);
              widget.onNavigate(AppScreen.details);
            },
          ),
        ),
      ],
    );
  }

  Widget _iconBox(IconData icon) {
    return Container(
      width: 52,
      height: 52,
      decoration: panelDecoration(widget.theme, widget.isDark, radius: 18),
      child: Icon(icon, color: widget.theme.text),
    );
  }

  Widget _insightPanel() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: widget.theme.surface,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
            color: widget.isDark
                ? AppColors.orange.withOpacity(.2)
                : widget.theme.border),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: widget.isDark
              ? [const Color(0xFF1F1F1F), const Color(0xFF0B0B0B)]
              : [const Color(0xFFF9FAFB), const Color(0xFFEFF3F8)],
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.monitor_heart_outlined, color: AppColors.orange),
              const SizedBox(width: 10),
              Expanded(
                  child: Text(widget.copy['ergonomics']!,
                      style: labelStyle(widget.theme.text, 11))),
              Text(widget.copy['weekly']!, style: labelStyle(AppColors.orange, 9)),
            ],
          ),
          const SizedBox(height: 14),
          RichText(
            text: TextSpan(
              style: TextStyle(
                color: widget.theme.body,
                fontSize: 13,
                height: 1.45,
                fontWeight: FontWeight.w500,
              ),
              children: widget.isRtl
                  ? const [
                      TextSpan(text: 'زادت وتيرة الوضعيات الحركية الخطرة بنسبة '),
                      TextSpan(
                        text: '12%',
                        style: TextStyle(color: AppColors.orange, fontWeight: FontWeight.w800),
                      ),
                      TextSpan(text: ' في المنطقة ب هذا الأسبوع.'),
                    ]
                  : const [
                      TextSpan(text: 'High-risk posture frequency increased by '),
                      TextSpan(
                        text: '12%',
                        style: TextStyle(color: AppColors.orange, fontWeight: FontWeight.w800),
                      ),
                      TextSpan(text: ' in Zone B this week.'),
                    ],
            ),
          ),
          const SizedBox(height: 14),
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(
              value: .65,
              minHeight: 6,
              color: AppColors.orange,
              backgroundColor:
                  widget.isDark ? Colors.white10 : const Color(0xFFDCE3EC),
            ),
          ),
        ],
      ),
    );
  }
}
