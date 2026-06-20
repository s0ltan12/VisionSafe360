import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../shared/widgets/vision_safe_logo.dart';

class LoadingScreen extends StatelessWidget {
  const LoadingScreen({
    super.key,
    required this.theme,
    required this.copy,
    required this.loadingProgress,
    required this.isDark,
  });

  final AppTheme theme;
  final Map<String, String> copy;
  final int loadingProgress;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 48),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const AnimatedLogo(size: 190),
          const SizedBox(height: 42),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      loadingProgress < 60 ? copy['initializing']! : copy['booting']!,
                      style: labelStyle(AppColors.orange, 10),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      'SECURE_HANDSHAKE_V4.2... OK',
                      style: TextStyle(
                        color: theme.muted,
                        fontSize: 9,
                        fontWeight: FontWeight.w700,
                        letterSpacing: .6,
                        fontFamily: 'monospace',
                      ),
                    ),
                  ],
                ),
              ),
              Text(
                '$loadingProgress%',
                style: const TextStyle(
                  color: AppColors.orange,
                  fontSize: 12,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(
              minHeight: 4,
              value: loadingProgress / 100,
              color: AppColors.orange,
              backgroundColor: isDark ? Colors.white10 : const Color(0xFFE2E8F0),
            ),
          ),
          const Spacer(),
          Padding(
            padding: const EdgeInsets.only(bottom: 40),
            child: Text(
              'VisionSafe Enterprise',
              style: labelStyle(theme.muted, 9),
            ),
          ),
        ],
      ),
    );
  }
}
