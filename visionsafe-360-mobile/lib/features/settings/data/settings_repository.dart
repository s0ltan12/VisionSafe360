class SettingsRepository {
  String _languageCode = 'en';
  bool _isDark = true;

  String get languageCode => _languageCode;
  bool get isDark => _isDark;

  void setLanguageCode(String value) {
    _languageCode = value;
  }

  void setIsDark(bool value) {
    _isDark = value;
  }
}
