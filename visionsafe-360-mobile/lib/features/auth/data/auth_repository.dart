import '../../../core/network/api_client.dart';
import '../../../core/network/endpoints.dart';
import '../../../core/network/token_storage.dart';
import '../../../shared/models/user.dart';

class AuthRepository {
  AuthRepository({
    required ApiClient apiClient,
    required TokenStorage tokenStorage,
  })  : _apiClient = apiClient,
        _tokenStorage = tokenStorage;

  final ApiClient _apiClient;
  final TokenStorage _tokenStorage;
  UserProfile? _currentUser;

  UserProfile? get currentUser => _currentUser;

  Future<UserProfile?> login({
    required String username,
    required String password,
  }) async {
    if (username.trim().isEmpty || password.isEmpty) return null;

    final response = await _apiClient.post(
      Endpoints.login,
      body: {
        'username': username.trim(),
        'password': password,
      },
    );
    final data = _authPayload(response);
    final token = (data['token'] ?? data['accessToken'] ?? data['jwt'])?.toString();
    if (token == null || token.isEmpty) {
      throw const ApiException('Login response did not include an auth token.');
    }

    await _tokenStorage.saveToken(token);
    _currentUser = UserProfile.fromJson(_asMap(data['user'] ?? data['profile']));
    return _currentUser;
  }

  Future<UserProfile?> loadProfileFromStoredToken() async {
    final token = await _tokenStorage.readToken();
    if (token == null || token.isEmpty) return null;

    final response = await _apiClient.get(Endpoints.profile);
    _currentUser = UserProfile.fromJson(_userPayload(response));
    return _currentUser;
  }

  Future<void> logout() async {
    _currentUser = null;
    await _tokenStorage.clearToken();
  }
}

Map<String, dynamic> _asMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}

Map<String, dynamic> _authPayload(Object? value) {
  final map = _asMap(value);
  final nested = _asMap(map['data']);
  return nested.isEmpty ? map : nested;
}

Map<String, dynamic> _userPayload(Object? value) {
  final map = _authPayload(value);
  final user = _asMap(map['user'] ?? map['profile']);
  return user.isEmpty ? map : user;
}
