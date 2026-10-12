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
            .having((error) => error.message, 'message', contains('Sign in')),
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
                (error) => error.message, 'message', 'Restaurant unavailable'),
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
                contains('Try again shortly')),
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
                'Razorpay is not configured'),
      ),
    );
  });
}
