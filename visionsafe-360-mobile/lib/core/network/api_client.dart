import 'package:dio/dio.dart';

import 'token_storage.dart';

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode, this.data});

  final String message;
  final int? statusCode;
  final Object? data;

  @override
  String toString() => 'ApiException($statusCode): $message';
}

class ApiClient {
  ApiClient({
    String? baseUrl,
    TokenStorage? tokenStorage,
    Dio? dio,
  })  : tokenStorage = tokenStorage ?? TokenStorage(),
        dio = dio ??
            Dio(
              BaseOptions(
                baseUrl: baseUrl ??
                    const String.fromEnvironment(
                      'API_BASE_URL',
                      defaultValue: 'http://localhost:3001',
                    ),
                connectTimeout: const Duration(seconds: 15),
                receiveTimeout: const Duration(seconds: 20),
                sendTimeout: const Duration(seconds: 20),
                headers: const {
                  'Accept': 'application/json',
                  'Content-Type': 'application/json',
                },
              ),
            ) {
    this.dio.interceptors.addAll([
          InterceptorsWrapper(
            onRequest: (options, handler) async {
              final token = await this.tokenStorage.readToken();
              if (token != null && token.isNotEmpty) {
                options.headers['Authorization'] = 'Bearer $token';
              }
              handler.next(options);
            },
            onError: (error, handler) {
              handler.next(error);
            },
          ),
          LogInterceptor(
            requestBody: true,
            responseBody: true,
          ),
        ]);
  }

  final Dio dio;
  final TokenStorage tokenStorage;

  Future<dynamic> get(
    String path, {
    Map<String, String>? headers,
    Map<String, dynamic>? query,
  }) async {
    return _request(
      () => dio.get<dynamic>(
        path,
        queryParameters: query,
        options: Options(headers: headers),
      ),
    );
  }

  Future<dynamic> post(
    String path, {
    Map<String, String>? headers,
    Map<String, dynamic>? body,
  }) async {
    return _request(
      () => dio.post<dynamic>(
        path,
        data: body,
        options: Options(headers: headers),
      ),
    );
  }

  Future<dynamic> patch(
    String path, {
    Map<String, String>? headers,
    Map<String, dynamic>? body,
  }) async {
    return _request(
      () => dio.patch<dynamic>(
        path,
        data: body,
        options: Options(headers: headers),
      ),
    );
  }

  Future<dynamic> _request(Future<Response<dynamic>> Function() request) async {
    try {
      final response = await request();
      return response.data;
    } on DioException catch (error) {
      throw ApiException(
        _messageFor(error),
        statusCode: error.response?.statusCode,
        data: error.response?.data,
      );
    }
  }

  String _messageFor(DioException error) {
    final data = error.response?.data;
    if (data is Map<String, dynamic>) {
      final message = data['message'] ?? data['error'] ?? data['detail'];
      if (message != null) return message.toString();
    }
    if (error.message != null && error.message!.isNotEmpty) {
      return error.message!;
    }
    return 'Network request failed';
  }
}
