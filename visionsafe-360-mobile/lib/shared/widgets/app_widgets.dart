import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../models/safety_alert.dart';

Color statusColor(AlertStatus status) {
  return switch (status) {
    AlertStatus.fresh => AppColors.orange,
    AlertStatus.acknowledged => AppColors.orange,
    AlertStatus.resolved => AppColors.success,
  };
}

Widget severityBadge(Severity severity) {
  final color = switch (severity) {
    Severity.critical => AppColors.danger,
    Severity.medium => AppColors.warning,
    Severity.low => const Color(0xFF3B82F6),
  };
  return appBadge(severityText(severity), color);
}

Widget statusBadge(AlertStatus status) {
  final color = statusColor(status);
  return appBadge(statusText(status), color, filled: status == AlertStatus.fresh);
}

Widget appBadge(String text, Color color, {bool filled = false}) {
  return Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    decoration: BoxDecoration(
      color: filled ? color : color.withOpacity(.14),
      borderRadius: BorderRadius.circular(999),
      border: Border.all(color: color.withOpacity(.35)),
    ),
    child: Text(
      text,
      style: TextStyle(
        color: filled ? const Color(0xFF101010) : color,
        fontSize: 9,
        fontWeight: FontWeight.w900,
        letterSpacing: .8,
      ),
    ),
  );
}

Widget primaryButton(
  String label,
  VoidCallback onTap, {
  IconData? icon,
  Color color = AppColors.orange,
  Color foreground = const Color(0xFF101010),
}) {
  return SizedBox(
    width: double.infinity,
    height: 58,
    child: ElevatedButton(
      onPressed: onTap,
      style: ElevatedButton.styleFrom(
        backgroundColor: color,
        foregroundColor: foreground,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 22),
            const SizedBox(width: 10),
          ],
          Text(label, style: labelStyle(foreground, 12)),
        ],
      ),
    ),
  );
}

Widget inlineMeta(
  IconData icon,
  String text,
  AppTheme theme, {
  bool compact = false,
}) {
  return Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Icon(icon, size: compact ? 13 : 16, color: AppColors.orange),
      const SizedBox(width: 5),
      Flexible(
        child: Text(
          text,
          overflow: TextOverflow.ellipsis,
          style: labelStyle(theme.muted, compact ? 9 : 10),
        ),
      ),
    ],
  );
}
