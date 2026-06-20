import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../../core/utils/provider_status.dart';
import '../../../shared/models/safety_alert.dart';
import '../data/incident_repository.dart';

class IncidentProvider extends ChangeNotifier {
  IncidentProvider(this._repository) : _alerts = _repository.loadInitialAlerts();

  final IncidentRepository _repository;

  List<SafetyAlert> _alerts;
  SafetyAlert? _selectedAlert;
  Severity? _historyFilter;
  bool _showNotification = false;
  bool _showResolveSheet = false;
  bool _isLoading = false;
  String? _error;
  ProviderStatus _status = ProviderStatus.idle;
  Timer? _notificationTimer;

  List<SafetyAlert> get alerts => List.unmodifiable(_alerts);
  SafetyAlert? get selectedAlert => _selectedAlert;
  Severity? get historyFilter => _historyFilter;
  bool get showNotification => _showNotification;
  bool get showResolveSheet => _showResolveSheet;
  bool get isLoading => _isLoading;
  String? get error => _error;
  ProviderStatus get status => _status;

  List<SafetyAlert> get activeAlerts =>
      _alerts.where((alert) => alert.status != AlertStatus.resolved).toList();

  List<SafetyAlert> get filteredHistory {
    if (_historyFilter == null) return alerts;
    return _alerts.where((alert) => alert.severity == _historyFilter).toList();
  }

  void scheduleNotification({required bool Function() shouldShow}) {
    _notificationTimer?.cancel();
    _notificationTimer = Timer(const Duration(seconds: 6), () {
      if (shouldShow()) {
        _showNotification = true;
        notifyListeners();
      }
    });
  }

  void cancelNotification() {
    _notificationTimer?.cancel();
  }

  void hideNotification() {
    _showNotification = false;
    notifyListeners();
  }

  void selectAlert(SafetyAlert alert) {
    _selectedAlert = alert;
    _showNotification = false;
    notifyListeners();
    loadIncidentDetails(alert.id);
  }

  void setHistoryFilter(Severity? severity) {
    _historyFilter = severity;
    notifyListeners();
  }

  void showResolveSheet() {
    _showResolveSheet = true;
    notifyListeners();
  }

  void hideResolveSheet() {
    _showResolveSheet = false;
    notifyListeners();
  }

  Future<void> loadIncidents() async {
    _setLoading();
    try {
      final alerts = await _repository.getIncidents();
      if (alerts.isNotEmpty) _alerts = alerts;
      _error = null;
      _status = ProviderStatus.success;
    } catch (error) {
      _error = error.toString();
      _status = ProviderStatus.error;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> loadHistory() async {
    _setLoading();
    try {
      final alerts = await _repository.getHistory();
      if (alerts.isNotEmpty) _alerts = alerts;
      _error = null;
      _status = ProviderStatus.success;
    } catch (error) {
      _error = error.toString();
      _status = ProviderStatus.error;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> loadIncidentDetails(String id) async {
    try {
      final alert = await _repository.getIncidentById(id);
      _replaceAlert(alert);
      _selectedAlert = alert;
      _error = null;
      _status = ProviderStatus.success;
      notifyListeners();
    } catch (error) {
      _error = error.toString();
      _status = ProviderStatus.error;
      notifyListeners();
    }
  }

  Future<void> acknowledge({
    required String id,
    required String timestamp,
    required String userName,
  }) async {
    _setLoading();
    try {
      final updated = await _repository.acknowledgeIncident(id);
      _replaceAlert(updated);
      _selectedAlert = updated;
      _error = null;
      _status = ProviderStatus.success;
    } catch (error) {
      _alerts = _repository.acknowledgeFallback(
        alerts: _alerts,
        id: id,
        timestamp: timestamp,
        userName: userName,
      );
      _selectedAlert = _alerts.firstWhere((alert) => alert.id == id);
      _error = error.toString();
      _status = ProviderStatus.error;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> resolve({
    required String id,
    required String action,
    required String timestamp,
    required String userName,
  }) async {
    _setLoading();
    try {
      final updated = await _repository.resolveIncident(id: id, action: action);
      _replaceAlert(updated);
      _selectedAlert = updated;
      _error = null;
      _status = ProviderStatus.success;
    } catch (error) {
      _alerts = _repository.resolveFallback(
        alerts: _alerts,
        id: id,
        action: action,
        timestamp: timestamp,
        userName: userName,
      );
      _selectedAlert = _alerts.firstWhere((alert) => alert.id == id);
      _error = error.toString();
      _status = ProviderStatus.error;
    } finally {
      _showResolveSheet = false;
      _isLoading = false;
      notifyListeners();
    }
  }

  void resetSessionUi() {
    _selectedAlert = null;
    _showNotification = false;
    _showResolveSheet = false;
    _error = null;
    _status = ProviderStatus.idle;
    cancelNotification();
    notifyListeners();
  }

  @override
  void dispose() {
    _notificationTimer?.cancel();
    super.dispose();
  }

  void _replaceAlert(SafetyAlert updated) {
    _alerts = _alerts.map((alert) => alert.id == updated.id ? updated : alert).toList();
  }

  void _setLoading() {
    _isLoading = true;
    _error = null;
    _status = ProviderStatus.loading;
    notifyListeners();
  }
}
