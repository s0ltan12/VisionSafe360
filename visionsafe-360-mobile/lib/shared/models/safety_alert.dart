enum Severity { critical, medium, low }

enum AlertStatus { fresh, acknowledged, resolved }

class TimelineEvent {
  const TimelineEvent({
    required this.status,
    required this.timestamp,
    this.user,
    this.note,
  });

  final AlertStatus status;
  final String timestamp;
  final String? user;
  final String? note;

  factory TimelineEvent.fromJson(Map<String, dynamic> json) {
    return TimelineEvent(
      status: alertStatusFromString(json['status']),
      timestamp: (json['timestamp'] ?? json['occurredAt'] ?? json['createdAt'] ?? '').toString(),
      user: json['user']?.toString() ?? json['userName']?.toString(),
      note: json['note']?.toString(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'status': statusText(status),
      'timestamp': timestamp,
      if (user != null) 'user': user,
      if (note != null) 'note': note,
    };
  }
}

class SafetyAlert {
  const SafetyAlert({
    required this.id,
    required this.type,
    required this.severity,
    required this.cameraName,
    required this.location,
    required this.timestamp,
    required this.timeAgo,
    required this.status,
    required this.snapshot,
    required this.confidence,
    required this.description,
    required this.timeline,
    this.actionTaken,
  });

  final String id;
  final String type;
  final Severity severity;
  final String cameraName;
  final String location;
  final String timestamp;
  final String timeAgo;
  final AlertStatus status;
  final String snapshot;
  final double confidence;
  final String description;
  final List<TimelineEvent> timeline;
  final String? actionTaken;

  factory SafetyAlert.fromJson(Map<String, dynamic> json) {
    return SafetyAlert(
      id: (json['id'] ?? '').toString(),
      type: (json['type'] ?? json['alertType'] ?? json['eventType'] ?? '').toString(),
      severity: severityFromString(json['severity']),
      cameraName: (json['cameraName'] ?? json['camera'] ?? json['camera_id'] ?? '').toString(),
      location: (json['location'] ?? json['zone'] ?? '').toString(),
      timestamp: (json['timestamp'] ?? json['occurredAt'] ?? json['createdAt'] ?? '').toString(),
      timeAgo: (json['timeAgo'] ?? '').toString(),
      status: alertStatusFromString(json['status']),
      snapshot: (json['snapshot'] ?? json['snapshotUrl'] ?? json['imageUrl'] ?? '').toString(),
      confidence: _asDouble(json['confidence']),
      description: (json['description'] ?? '').toString(),
      actionTaken: json['actionTaken']?.toString(),
      timeline: _timelineFromJson(json['timeline'] ?? json['events']),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'type': type,
      'severity': severityText(severity),
      'cameraName': cameraName,
      'location': location,
      'timestamp': timestamp,
      'timeAgo': timeAgo,
      'status': statusText(status),
      'snapshot': snapshot,
      'confidence': confidence,
      'description': description,
      if (actionTaken != null) 'actionTaken': actionTaken,
      'timeline': timeline.map((event) => event.toJson()).toList(),
    };
  }

  SafetyAlert copyWith({
    AlertStatus? status,
    List<TimelineEvent>? timeline,
    String? actionTaken,
  }) {
    return SafetyAlert(
      id: id,
      type: type,
      severity: severity,
      cameraName: cameraName,
      location: location,
      timestamp: timestamp,
      timeAgo: timeAgo,
      status: status ?? this.status,
      snapshot: snapshot,
      confidence: confidence,
      description: description,
      timeline: timeline ?? this.timeline,
      actionTaken: actionTaken ?? this.actionTaken,
    );
  }
}

String severityText(Severity severity) {
  return switch (severity) {
    Severity.critical => 'Critical',
    Severity.medium => 'Medium',
    Severity.low => 'Low',
  };
}

Severity severityFromString(Object? value) {
  final normalized = value.toString().toLowerCase();
  if (normalized.contains('critical') || normalized.contains('high')) {
    return Severity.critical;
  }
  if (normalized.contains('medium')) return Severity.medium;
  return Severity.low;
}

String statusText(AlertStatus status) {
  return switch (status) {
    AlertStatus.fresh => 'New',
    AlertStatus.acknowledged => 'Acknowledged',
    AlertStatus.resolved => 'Resolved',
  };
}

AlertStatus alertStatusFromString(Object? value) {
  final normalized = value.toString().toLowerCase();
  if (normalized.contains('ack')) return AlertStatus.acknowledged;
  if (normalized.contains('resolved') || normalized.contains('closed')) {
    return AlertStatus.resolved;
  }
  return AlertStatus.fresh;
}

List<TimelineEvent> _timelineFromJson(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => TimelineEvent.fromJson(Map<String, dynamic>.from(item)))
      .toList();
}

double _asDouble(Object? value) {
  if (value is double) return value;
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value) ?? 0;
  return 0;
}
