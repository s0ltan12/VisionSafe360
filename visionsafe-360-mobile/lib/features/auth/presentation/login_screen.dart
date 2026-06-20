import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../shared/providers/app_providers.dart';
import '../../../shared/widgets/app_widgets.dart';
import '../../../shared/widgets/vision_safe_logo.dart';

class LoginScreen extends StatelessWidget {
  const LoginScreen({
    super.key,
    required this.theme,
    required this.copy,
    required this.onLoggedIn,
  });

  final AppTheme theme;
  final Map<String, String> copy;
  final VoidCallback onLoggedIn;

  @override
  Widget build(BuildContext context) {
    final auth = context.authProvider;

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(32, 72, 32, 32),
      child: Column(
        children: [
          const AnimatedLogo(size: 156),
          const SizedBox(height: 16),
          RichText(
            text: TextSpan(
              style: TextStyle(
                color: theme.text,
                fontSize: 30,
                fontWeight: FontWeight.w900,
                letterSpacing: .2,
              ),
              children: const [
                TextSpan(text: 'VisionSafe '),
                TextSpan(text: '360', style: TextStyle(color: AppColors.orange)),
              ],
            ),
          ),
          const SizedBox(height: 8),
          Text('Mobile Response Unit', style: labelStyle(theme.muted, 11)),
          const SizedBox(height: 58),
          _fieldLabel(copy['username']!),
          const SizedBox(height: 8),
          _inputField(
            icon: Icons.person_outline,
            hint: 'safety_officer_7',
            onChanged: auth.setLoginEmail,
          ),
          const SizedBox(height: 22),
          _fieldLabel(copy['password']!),
          const SizedBox(height: 8),
          _inputField(
            icon: Icons.shield_outlined,
            hint: '........',
            obscure: true,
            onChanged: auth.setLoginPass,
          ),
          const SizedBox(height: 26),
          primaryButton(copy['login']!, () async {
            final success = await auth.login();
            if (success) onLoggedIn();
          }),
          const SizedBox(height: 38),
          Text(
            'Secure Industrial Protocol v4.2',
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
    );
  }

  Widget _fieldLabel(String text) {
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: Padding(
        padding: const EdgeInsetsDirectional.only(start: 4),
        child: Text(text, style: labelStyle(theme.muted, 10)),
      ),
    );
  }

  Widget _inputField({
    required IconData icon,
    required String hint,
    required ValueChanged<String> onChanged,
    bool obscure = false,
  }) {
    return TextField(
      obscureText: obscure,
      onChanged: onChanged,
      style: TextStyle(color: theme.text, fontSize: 14),
      decoration: InputDecoration(
        filled: true,
        fillColor: theme.input,
        hintText: hint,
        hintStyle: TextStyle(color: theme.muted),
        prefixIcon: Icon(icon, color: theme.muted),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: BorderSide(color: theme.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: AppColors.orange),
        ),
      ),
    );
  }
}
