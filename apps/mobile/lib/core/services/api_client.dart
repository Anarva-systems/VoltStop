import 'dart:io' show HandshakeException, SocketException;

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
        if (options.extra['skipAuth'] == true) {
          handler.next(options);
          return;
        }
        final token = await _accessToken();
        if (token == null || token.isEmpty) {
          handler.reject(DioException(
            requestOptions: options,
            type: DioExceptionType.cancel,
            error: const ApiException(
              'Your sign-in session is missing. Sign in again and retry.',
              category: 'authentication',
            ),
          ));
          return;
        }
        options.headers['Authorization'] = 'Bearer $token';
        handler.next(options);
      },
    ));
  }

  final Future<String?> Function() _accessToken;
  late final Dio dio;

  Future<dynamic> get(String path, {Map<String, dynamic>? query}) =>
      _request(() => dio.get<dynamic>(path, queryParameters: query));

  /// Confirms the API and its required services are ready before phone auth.
  /// The readiness endpoint is intentionally public and does not need a token.
  Future<void> checkReadiness() async {
    await _request(() => dio.get<dynamic>(
          '/ready',
          options: Options(extra: const {'skipAuth': true}),
        ));
  }

  Future<dynamic> post(String path,
          {Object? data, Map<String, String>? headers}) =>
      _request(() => dio.post<dynamic>(path,
          data: data, options: Options(headers: headers)));

  Future<dynamic> patch(String path, {Object? data}) =>
      _request(() => dio.patch<dynamic>(path, data: data));

  Future<dynamic> put(String path, {Object? data}) =>
      _request(() => dio.put<dynamic>(path, data: data));

  Future<dynamic> delete(String path) =>
      _request(() => dio.delete<dynamic>(path));

  Future<dynamic> _request(Future<Response<dynamic>> Function() request) async {
    try {
      return _unwrap(await request());
    } on DioException catch (error) {
      if (error.error is ApiException) throw error.error as ApiException;
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
          category: 'authentication',
        );
      }
      if (status == 403) {
        throw ApiException(
          'You do not have permission to access this information.',
          statusCode: status,
          code: bodyCode,
          category: 'authorization',
        );
      }
      final deploymentMissing =
          bodyCode?.toUpperCase() == 'DEPLOYMENT_NOT_FOUND' ||
              (bodyMessage?.toLowerCase().contains(
                        'deployment could not be found on vercel',
                      ) ??
                  false);
      if (status == 404 && deploymentMissing) {
        throw ApiException(
          'The VoltStop API deployment could not be found on Vercel. The API owner must restore the deployment before your profile can load.',
          statusCode: status,
          code: bodyCode,
          category: 'deployment_unavailable',
        );
      }
      if (status == 404) {
        throw ApiException(
          bodyMessage ?? 'This route, menu, or order is no longer available.',
          statusCode: status,
          code: bodyCode,
          category: 'not_found',
        );
      }
      if (status == 422) {
        throw ApiException(
          bodyMessage ?? 'Check the information and try again.',
          statusCode: status,
          code: bodyCode,
          category: 'validation',
        );
      }
      if (bodyCode == 'DEPENDENCIES_UNAVAILABLE') {
        throw ApiException(
          'VoltStop services are not ready. Try again shortly.',
          statusCode: status,
          code: bodyCode,
          category: 'readiness',
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
          category: 'server',
        );
      }
      if (status != null) {
        throw ApiException(
          bodyMessage ??
              'The request could not be completed. Please try again.',
          statusCode: status,
          code: bodyCode,
          category: 'request',
        );
      }
      throw _networkException(error);
    }
  }

  ApiException _networkException(DioException error) {
    final cause = error.error;
    if (cause is HandshakeException) {
      return const ApiException(
        'VoltStop could not establish a secure connection. Retry on a trusted network.',
        category: 'tls',
      );
    }
    if (cause is SocketException) {
      final details = cause.message.toLowerCase();
      final dnsFailure = details.contains('failed host lookup') ||
          details.contains('name or service not known') ||
          details.contains('nodename nor servname');
      return ApiException(
        dnsFailure
            ? 'The API address could not be found. Check internet access and retry.'
            : 'VoltStop could not be reached. Check internet access and the API address, then retry.',
        category: dnsFailure ? 'dns' : 'network',
      );
    }
    switch (error.type) {
      case DioExceptionType.connectionTimeout:
        return const ApiException(
          'The connection to VoltStop timed out. Check your network and retry.',
          category: 'timeout',
        );
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
        return const ApiException(
          'VoltStop did not respond in time. Retry in a moment.',
          category: 'timeout',
        );
      case DioExceptionType.badCertificate:
        return const ApiException(
          'VoltStop could not establish a secure connection. Check the app URL or network and retry.',
          category: 'tls',
        );
      case DioExceptionType.connectionError:
        return const ApiException(
          'VoltStop could not be reached. Check internet access and the API address, then retry.',
          category: 'network',
        );
      case DioExceptionType.unknown:
        if (error.error is HandshakeException) {
          return const ApiException(
            'VoltStop could not establish a secure connection. Retry on a trusted network.',
            category: 'tls',
          );
        }
        if (error.error is SocketException) {
          return const ApiException(
            'VoltStop could not be reached. Check internet access and DNS, then retry.',
            category: 'network',
          );
        }
        return const ApiException(
          'The request could not reach VoltStop. Check the API address and network, then retry.',
          category: 'network',
        );
      case DioExceptionType.badResponse:
      case DioExceptionType.cancel:
        return const ApiException(
          'The request could not be completed. Retry in a moment.',
          category: 'network',
        );
    }
  }

  dynamic _unwrap(Response<dynamic> response) {
    final body = response.data;
    if (body is Map<String, dynamic>) {
      if (body['success'] == false) {
        final error = body['error'];
        throw ApiException(
          error is Map
              ? '${error['message'] ?? 'Request failed'}'
              : 'Request failed',
          statusCode: response.statusCode,
          code: error is Map && error['code'] is String
              ? error['code'] as String
              : null,
          category: _categoryForStatus(response.statusCode),
        );
      }
      return body.containsKey('data') ? body['data'] : body;
    }
    return body;
  }
}

String _categoryForStatus(int? status) {
  if (status == 401) return 'authentication';
  if (status == 403) return 'authorization';
  if (status == 404) return 'not_found';
  if (status != null && status >= 500) return 'server';
  return 'request';
}

class ApiException implements Exception {
  const ApiException(this.message,
      {this.statusCode, this.code, this.category = 'request'});
  final String message;
  final int? statusCode;
  final String? code;
  final String category;
  @override
  String toString() => message;
}
