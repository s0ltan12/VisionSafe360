class SocketService {
  const SocketService();

  static const criticalAlertEvent = 'critical_alert';

  Future<void> connect() async {
    throw UnimplementedError('Realtime integration will be added later.');
  }

  Future<void> disconnect() async {
    throw UnimplementedError('Realtime integration will be added later.');
  }

  Stream<CriticalAlertEvent> get criticalAlerts {
    throw UnimplementedError('Realtime integration will be added later.');
  }
}

class CriticalAlertEvent {
  const CriticalAlertEvent({
    required this.title,
    required this.description,
    required this.camera,
    required this.timestamp,
  });

  final String title;
  final String description;
  final String camera;
  final DateTime timestamp;

  factory CriticalAlertEvent.fromJson(Map<String, dynamic> json) {
    return CriticalAlertEvent(
      title: (json['title'] ?? '').toString(),
      description: (json['desc'] ?? json['description'] ?? '').toString(),
      camera: (json['camera'] ?? '').toString(),
      timestamp: DateTime.tryParse((json['timestamp'] ?? '').toString()) ??
          DateTime.fromMillisecondsSinceEpoch(0),
    );
  }
}
