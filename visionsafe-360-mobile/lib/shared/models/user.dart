class UserProfile {
  const UserProfile({
    required this.name,
    required this.role,
    required this.email,
    required this.level,
  });

  final String name;
  final String role;
  final String email;
  final int level;

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      name: (json['name'] ?? json['fullName'] ?? '').toString(),
      role: (json['role'] ?? '').toString(),
      email: (json['email'] ?? '').toString(),
      level: _asInt(json['level']),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'role': role,
      'email': email,
      'level': level,
    };
  }
}

int _asInt(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value) ?? 0;
  return 0;
}
