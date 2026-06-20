import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../shared/models/safety_alert.dart';
import '../../../shared/widgets/app_widgets.dart';

class IncidentTile extends StatelessWidget {
  const IncidentTile({
    super.key,
    required this.alert,
    required this.theme,
    required this.isDark,
    required this.isRtl,
    required this.onTap,
    this.large = false,
  });

  final SafetyAlert alert;
  final AppTheme theme;
  final bool isDark;
  final bool isRtl;
  final VoidCallback onTap;
  final bool large;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(22),
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: panelDecoration(theme, isDark, radius: 22),
            child: Row(
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(large ? 16 : 13),
                  child: Image.network(
                    alert.snapshot,
                    width: large ? 64 : 56,
                    height: large ? 64 : 56,
                    fit: BoxFit.cover,
                    color: isDark ? Colors.black.withOpacity(.18) : null,
                    colorBlendMode: BlendMode.darken,
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(child: Text(alert.type, style: itemTitleStyle(theme))),
                          large ? severityBadge(alert.severity) : statusBadge(alert.status),
                        ],
                      ),
                      const SizedBox(height: 7),
                      inlineMeta(
                        Icons.location_on_outlined,
                        alert.location,
                        theme,
                        compact: true,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 6),
                Icon(
                  isRtl ? Icons.chevron_left : Icons.chevron_right,
                  color: theme.muted,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

BoxDecoration panelDecoration(AppTheme theme, bool isDark, {double radius = 24}) {
  return BoxDecoration(
    color: theme.surface,
    borderRadius: BorderRadius.circular(radius),
    border: Border.all(color: theme.border),
    boxShadow: isDark
        ? null
        : [
            BoxShadow(
              color: Colors.black.withOpacity(.04),
              blurRadius: 18,
              offset: const Offset(0, 8),
            ),
          ],
  );
}

TextStyle titleStyle(AppTheme theme, double size) {
  return TextStyle(
    color: theme.text,
    fontSize: size,
    fontWeight: FontWeight.w900,
    letterSpacing: .1,
    height: 1.08,
  );
}

TextStyle itemTitleStyle(AppTheme theme, [double size = 13]) {
  return TextStyle(
    color: theme.text,
    fontSize: size,
    fontWeight: FontWeight.w900,
    letterSpacing: .2,
    overflow: TextOverflow.ellipsis,
  );
}
