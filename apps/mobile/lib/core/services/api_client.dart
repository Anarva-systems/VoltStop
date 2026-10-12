import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import '../config/app_config.dart';

class ApiClient {
  ApiClient({required Future<String?> Function() accessToken})
      : _accessToken = accessToken {
    dio = Dio(BaseOptions(
      baseUrl: AppConfig.apiBaseUrl,
      connectTimeout: const Duration(seconds: 8),
      receiveTimeout: const Duration(seconds: 12),
      headers: const {'Accept': 'application/json'},
    ));
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await _accessToken();
        if (token != null && token.isNotEmpty) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        handler.next(options);
      },
    ));
  }

  final Future<String?> Function() _accessToken;
  late final Dio dio;

  Future<dynamic> get(String path, {Map<String, dynamic>? query}) =>
      _request(() => dio.get<dynamic>(path, queryParameters: query));

  Future<dynamic> post(String path,
          {Object? data, Map<String, String>? headers}) =>
      _request(() => dio.post<dynamic>(path,
          data: data, options: Options(headers: headers)));

  Future<dynamic> patch(String path, {Object? data}) =>
      _request(() => dio.patch<dynamic>(path, data: data));

  Future<dynamic> delete(String path) =>
      _request(() => dio.delete<dynamic>(path));

  Future<dynamic> _request(Future<Response<dynamic>> Function() request) async {
    try {
      return _unwrap(await request());
    } on DioException catch (error) {
      final status = error.response?.statusCode;
      final responseError = error.response?.data;
      final bodyError = responseError is Map ? responseError['error'] : null;
      final bodyCode = bodyError is Map && bodyError['code'] is String
          ? bodyError['code'] as String
          : null;
      final bodyMessage = bodyError is Map && bodyError['message'] is String
          ? bodyError['message'] as String
          : null;
      if (kDebugMode) {
        debugPrint(
          'VoltStop API ${error.requestOptions.method} ${error.requestOptions.path} failed (${status == null ? 'network' : 'HTTP $status'}${bodyCode == null ? '' : ', $bodyCode'}).',
        );
      }
      if (status == 401) {
        throw ApiException(
          'Your session could not be verified. Sign in again and retry.',
          statusCode: status,
          code: bodyCode,
        );
      }
      if (status == 403) {
        throw ApiException(
          'You do not have permission to access this information.',
          statusCode: status,
          code: bodyCode,
        );
      }
      if (status == 404) {
        throw ApiException(
          bodyMessage ?? 'This route, menu, or order is no longer available.',
          statusCode: status,
          code: bodyCode,
        );
      }
      if (status == 422) {
        throw ApiException(
          bodyMessage ?? 'Check the information and try again.',
          statusCode: status,
          code: bodyCode,
        );
      }
      if (status != null && status >= 500) {
        final isUnexpected =
            bodyCode == null || bodyCode == 'INTERNAL_SERVER_ERROR';
        throw ApiException(
          isUnexpected
              ? 'VoltStop could not complete this request. Try again shortly.'
              : (bodyMessage ?? 'VoltStop could not complete this request.'),
          statusCode: status,
          code: bodyCode,
        );
      }
      if (status != null) {
        throw ApiException(
          bodyMessage ??
              'The request could not be completed. Please try again.',
          statusCode: status,
          code: bodyCode,
        );
      }
      throw const ApiException(
        'Could not reach VoltStop. Check your connection and try again.',
      );
    }
  }

  dynamic _unwrap(Response<dynamic> response) {
    final body = response.data;
    if (body is Map<String, dynamic>) {
      if (body['success'] == false) {
        final error = body['error'];
        throw ApiException(error is Map
            ? '${error['message'] ?? 'Request failed'}'
            : 'Request failed');
      }
      return body.containsKey('data') ? body['data'] : body;
    }
    return body;
  }
}

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode, this.code});
  final String message;
  final int? statusCode;
  final String? code;
  @override
  String toString() => message;
}
