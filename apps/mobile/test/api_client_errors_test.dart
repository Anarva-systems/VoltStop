import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voltstop_mobile/core/services/api_client.dart';

ApiClient clientReturning(int status, Map<String, dynamic> body) {
  final client = ApiClient(accessToken: () async => 'test-token');
  client.dio.interceptors.add(InterceptorsWrapper(
    onRequest: (options, handler) => handler.reject(
      DioException(
        requestOptions: options,
        response: Response<dynamic>(
          requestOptions: options,
          statusCode: status,
          data: body,
        ),
        type: DioExceptionType.badResponse,
      ),
    ),
  ));
  return client;
}

void main() {
  test('missing access token is reported as authentication before network IO',
      () async {
    var sent = false;
    final client = ApiClient(accessToken: () async => null);
    client.dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        sent = true;
        handler.next(options);
      },
    ));

    await expectLater(
      client.get('/profile'),
      throwsA(isA<ApiException>()
          .having((error) => error.category, 'category', 'authentication')),
    );
    expect(sent, isFalse);
  });

  test('DNS failures are identified separately from general network errors',
      () async {
    final client = ApiClient(accessToken: () async => 'test-token');
    client.dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) => handler.reject(
        DioException(
          requestOptions: options,
          type: DioExceptionType.connectionError,
          error: const SocketException('Failed host lookup: API host'),
        ),
      ),
    ));

    await expectLater(
      client.get('/profile'),
      throwsA(isA<ApiException>()
          .having((error) => error.category, 'category', 'dns')
          .having(
              (error) => error.message, 'message', contains('API address'))),
    );
  });

  test('connection timeout is distinct from server responses', () async {
    final client = ApiClient(accessToken: () async => 'test-token');
    client.dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) => handler.reject(
        DioException(
          requestOptions: options,
          type: DioExceptionType.connectionTimeout,
        ),
      ),
    ));

    await expectLater(
      client.get('/profile'),
      throwsA(isA<ApiException>()
          .having((error) => error.category, 'category', 'timeout')
          .having((error) => error.message, 'message', contains('timed out'))),
    );
  });

  test('unauthorized responses ask the customer to sign in again', () async {
    final client = clientReturning(401, {
      'success': false,
      'error': {'code': 'UNAUTHORIZED', 'message': 'Unauthorized'},
    });

    await expectLater(
      client.get('/restaurants/orders'),
      throwsA(
        isA<ApiException>()
            .having((error) => error.statusCode, 'status', 401)
            .having((error) => error.code, 'code', 'UNAUTHORIZED')
            .having((error) => error.message, 'message', contains('Sign in'))
            .having((error) => error.category, 'category', 'authentication'),
      ),
    );
  });

  test('not found responses preserve the safe API message', () async {
    final client = clientReturning(404, {
      'success': false,
      'error': {
        'code': 'RESTAURANT_NOT_FOUND',
        'message': 'Restaurant unavailable'
      },
    });

    await expectLater(
      client.get('/restaurants/unknown/menu'),
      throwsA(
        isA<ApiException>()
            .having((error) => error.statusCode, 'status', 404)
            .having(
                (error) => error.message, 'message', 'Restaurant unavailable')
            .having((error) => error.category, 'category', 'not_found'),
      ),
    );
  });

  test('unexpected server responses do not expose internal error details',
      () async {
    final client = clientReturning(500, {
      'success': false,
      'error': {
        'code': 'INTERNAL_SERVER_ERROR',
        'message': 'An unexpected error occurred'
      },
    });

    await expectLater(
      client.get('/routes/plan'),
      throwsA(
        isA<ApiException>()
            .having((error) => error.statusCode, 'status', 500)
            .having((error) => error.message, 'message',
                contains('Try again shortly'))
            .having((error) => error.category, 'category', 'server'),
      ),
    );
  });

  test('payment configuration errors remain actionable', () async {
    final client = clientReturning(503, {
      'success': false,
      'error': {
        'code': 'PAYMENT_UNAVAILABLE',
        'message': 'Razorpay is not configured'
      },
    });

    await expectLater(
      client.get('/restaurants/orders'),
      throwsA(
        isA<ApiException>()
            .having((error) => error.statusCode, 'status', 503)
            .having((error) => error.message, 'message',
                'Razorpay is not configured')
            .having((error) => error.category, 'category', 'server'),
      ),
    );
  });

  test('backend readiness failure is distinguished from an OTP error',
      () async {
    final client = clientReturning(503, {
      'success': false,
      'error': {
        'code': 'DEPENDENCIES_UNAVAILABLE',
        'message': 'One or more required services are unavailable',
      },
    });

    await expectLater(
      client.checkReadiness(),
      throwsA(
        isA<ApiException>()
            .having((error) => error.statusCode, 'status', 503)
            .having((error) => error.category, 'category', 'readiness')
            .having((error) => error.message, 'message',
                'VoltStop services are not ready. Try again shortly.'),
      ),
    );
  });
}
