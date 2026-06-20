import 'package:flutter/foundation.dart';

import '../../../core/constants/app_copy.dart';
import '../../../core/utils/provider_status.dart';
import '../data/settings_repository.dart';

class SettingsProvider extends ChangeNotifier {
  SettingsProvider(this._repository)
      : _languageCode = _repository.languageCode,
        _isDark = _repository.isDark;

  final SettingsRepository _repository;

  String _languageCode;
  bool _isDark;
  bool _isLoading = false;
  String? _error;
  ProviderStatus _status = ProviderStatus.idle;

  String get languageCode => _languageCode;
  bool get isDark => _isDark;
  bool get isRtl => _languageCode == 'ar';
  Map<String, String> get copy => appCopy[_languageCode]!;
  bool get isLoading => _isLoading;
  String? get error => _error;
  ProviderStatus get status => _status;

  void toggleLanguage() {
    _setSuccessState();
    _languageCode = _languageCode == 'en' ? 'ar' : 'en';
    _repository.setLanguageCode(_languageCode);
    notifyListeners();
  }

  void toggleTheme() {
    _setSuccessState();
    _isDark = !_isDark;
    _repository.setIsDark(_isDark);
    notifyListeners();
  }

  void _setSuccessState() {
    _isLoading = false;
    _error = null;
    _status = ProviderStatus.success;
  }
}
