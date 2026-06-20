import '../../../core/network/api_client.dart';
import '../../../core/network/endpoints.dart';
import '../../../shared/models/safety_alert.dart';

class IncidentRepository {
  IncidentRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  List<SafetyAlert> loadInitialAlerts() => mockInitialAlerts();

  Future<List<SafetyAlert>> getIncidents() async {
    final response = await _apiClient.get(Endpoints.incidents);
    return _alertsFromResponse(response);
  }

  Future<SafetyAlert> getIncidentById(String id) async {
    final response = await _apiClient.get(Endpoints.incidentById(id));
    return SafetyAlert.fromJson(_alertPayload(response));
  }

  Future<SafetyAlert> acknowledgeIncident(String id) async {
    final response = await _apiClient.post(Endpoints.acknowledgeIncident(id));
    return SafetyAlert.fromJson(_alertPayload(response));
  }

  Future<SafetyAlert> resolveIncident({
    required String id,
    required String action,
  }) async {
    final response = await _apiClient.post(
      Endpoints.resolveIncident(id),
      body: {'action': action},
    );
    return SafetyAlert.fromJson(_alertPayload(response));
  }

  Future<List<SafetyAlert>> getHistory() async {
    final response = await _apiClient.get(Endpoints.history);
    return _alertsFromResponse(response);
  }

  List<SafetyAlert> mockInitialAlerts() => const [
        SafetyAlert(
          id: 'ALT-1004',
          type: 'Fall Detected',
          severity: Severity.critical,
          cameraName: 'Cam 02 - Scaffold',
          location: 'Sector B - Floor 4',
          timestamp: '11:45:00 AM',
          timeAgo: 'Just now',
          status: AlertStatus.fresh,
          snapshot:
              'https://images.unsplash.com/photo-1541888946425-d81bb19240f5?auto=format&fit=crop&w=800&q=80',
          confidence: 96.2,
          description:
              'Sudden vertical displacement detected. Worker may have slipped on loose flooring.',
          timeline: [
            TimelineEvent(status: AlertStatus.fresh, timestamp: '11:45:00 AM'),
          ],
        ),
        SafetyAlert(
          id: 'ALT-1003',
          type: 'PPE Violation',
          severity: Severity.medium,
          cameraName: 'Cam 01 - Entrance',
          location: 'Main Gate',
          timestamp: '11:30:12 AM',
          timeAgo: '15m ago',
          status: AlertStatus.acknowledged,
          snapshot:
              'https://images.unsplash.com/photo-1587293852726-70cdb56c2866?auto=format&fit=crop&w=800&q=80',
          confidence: 98.4,
          description: 'Worker detected entering without industrial-grade hard hat.',
          timeline: [
            TimelineEvent(status: AlertStatus.fresh, timestamp: '11:30:12 AM'),
            TimelineEvent(
              status: AlertStatus.acknowledged,
              timestamp: '11:35:00 AM',
              user: 'Eng. Ahmed',
            ),
          ],
        ),
        SafetyAlert(
          id: 'ALT-1002',
          type: 'Proximity',
          severity: Severity.critical,
          cameraName: 'Cam 05 - Heavy Mach',
          location: 'Loading Bay',
          timestamp: '10:15:45 AM',
          timeAgo: '1h ago',
          status: AlertStatus.resolved,
          snapshot:
              'https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?auto=format&fit=crop&w=800&q=80',
          confidence: 91.5,
          description: 'Unauthorised personnel detected within the 2m exclusion zone.',
          actionTaken: 'Stopped work & cleared zone',
          timeline: [
            TimelineEvent(status: AlertStatus.fresh, timestamp: '10:15:45 AM'),
            TimelineEvent(
              status: AlertStatus.acknowledged,
              timestamp: '10:20:00 AM',
              user: 'Eng. Ahmed',
            ),
            TimelineEvent(
              status: AlertStatus.resolved,
              timestamp: '10:45:00 AM',
              user: 'Eng. Ahmed',
              note: 'Stopped work & cleared zone',
            ),
          ],
        ),
      ];

  List<SafetyAlert> acknowledgeFallback({
    required List<SafetyAlert> alerts,
    required String id,
    required String timestamp,
    required String userName,
  }) {
    final event = TimelineEvent(
      status: AlertStatus.acknowledged,
      timestamp: timestamp,
      user: userName,
    );
    return alerts.map((alert) {
      if (alert.id != id) return alert;
      return alert.copyWith(
        status: AlertStatus.acknowledged,
        timeline: [...alert.timeline, event],
      );
    }).toList();
  }

  List<SafetyAlert> resolveFallback({
    required List<SafetyAlert> alerts,
    required String id,
    required String action,
    required String timestamp,
    required String userName,
  }) {
    final event = TimelineEvent(
      status: AlertStatus.resolved,
      timestamp: timestamp,
      user: userName,
      note: action,
    );
    return alerts.map((alert) {
      if (alert.id != id) return alert;
      return alert.copyWith(
        status: AlertStatus.resolved,
        actionTaken: action,
        timeline: [...alert.timeline, event],
      );
    }).toList();
  }
}

List<SafetyAlert> _alertsFromResponse(Object? response) {
  final payload =
      response is Map ? response['data'] ?? response['incidents'] ?? response['items'] : response;
  if (payload is List) {
    return payload
        .whereType<Map>()
        .map((item) => SafetyAlert.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }
  return const [];
}

Map<String, dynamic> _asMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}

Map<String, dynamic> _alertPayload(Object? value) {
  final map = _asMap(value);
  final data = _asMap(map['data']);
  final source = data.isEmpty ? map : data;
  final incident = _asMap(source['incident'] ?? source['alert']);
  return incident.isEmpty ? source : incident;
}
