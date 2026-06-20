import 'package:flutter/foundation.dart';

import '../../../core/utils/provider_status.dart';
import '../../../shared/models/user.dart';
import '../data/auth_repository.dart';

class AuthProvider extends ChangeNotifier {
  AuthProvider(this._repository);

  final AuthRepository _repository;

  UserProfile? _user;
  String _loginEmail = '';
  String _loginPass = '';
  bool _isLoading = false;
  String? _error;
  ProviderStatus _status = ProviderStatus.idle;

  UserProfile? get user => _user;
  String get loginEmail => _loginEmail;
  String get loginPass => _loginPass;
  bool get isAuthenticated => _user != null;
  bool get isLoading => _isLoading;
  String? get error => _error;
  ProviderStatus get status => _status;

  void setLoginEmail(String value) {
    _loginEmail = value;
  }

  void setLoginPass(String value) {
    _loginPass = value;
  }

  Future<bool> login() async {
    _setLoading();
    try {
      final user = await _repository.login(
        username: _loginEmail,
        password: _loginPass,
      );
      if (user == null) {
        _isLoading = false;
        _status = ProviderStatus.idle;
        notifyListeners();
        return false;
      }
      _user = user;
      _error = null;
      _isLoading = false;
      _status = ProviderStatus.success;
      notifyListeners();
      return true;
    } catch (error) {
      _error = error.toString();
      _isLoading = false;
      _status = ProviderStatus.error;
      notifyListeners();
      return false;
    }
  }

  Future<void> restoreSession() async {
    _setLoading();
    try {
      _user = await _repository.loadProfileFromStoredToken();
      _error = null;
      _status = _user == null ? ProviderStatus.idle : ProviderStatus.success;
    } catch (error) {
      _error = error.toString();
      _user = null;
      _status = ProviderStatus.error;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    await _repository.logout();
    _user = null;
    _loginEmail = '';
    _loginPass = '';
    _error = null;
    _status = ProviderStatus.idle;
    notifyListeners();
  }

  void _setLoading() {
    _isLoading = true;
    _error = null;
    _status = ProviderStatus.loading;
    notifyListeners();
  }
}
