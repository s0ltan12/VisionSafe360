import 'package:flutter/material.dart';

class AppColors {
  static const orange = Color(0xFFFF6A00);
  static const lightOrange = Color(0xFFFF8A3A);
  static const success = Color(0xFF16A34A);
  static const warning = Color(0xFFCA8A04);
  static const danger = Color(0xFFDC2626);
}

class AppTheme {
  const AppTheme(this.dark);

  final bool dark;

  Color get bg => dark ? const Color(0xFF0A0A0A) : const Color(0xFFF4F6F8);
  Color get surface => dark ? const Color(0xFF141414) : const Color(0xFFFAFBFD);
  Color get nav => dark ? const Color(0xEE141414) : const Color(0xF7FAFBFD);
  Color get input => dark ? const Color(0xFF1F1F1F) : const Color(0xFFFAFBFD);
  Color get border => dark ? Colors.white.withOpacity(.08) : const Color(0xFFE2E8F0);
  Color get text => dark ? const Color(0xFFF8FAFC) : const Color(0xFF111827);
  Color get body => dark ? const Color(0xFFD1D5DB) : const Color(0xFF475569);
  Color get muted => dark ? const Color(0xFF8B949E) : const Color(0xFF64748B);
}

TextStyle labelStyle(Color color, double size) {
  return TextStyle(
    color: color,
    fontSize: size,
    fontWeight: FontWeight.w900,
    letterSpacing: .8,
  );
}
