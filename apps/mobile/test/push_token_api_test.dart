import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:supabase_flutter/supabase_flutter.dart' show SupabaseClient;
import 'package:voltstop_mobile/core/services/api_client.dart';
import 'package:voltstop_mobile/repositories/driver_repository.dart';

void main() {
  const deviceToken = 'dXk9_:abc-123=456DEF';

  test('push token registration uses the authenticated REST upsert', () async {
    final adapter = _PushApiAdapter();
    final api = ApiClient(accessToken: () async => 'verified-access-token');
    api.dio.httpClientAdapter = adapter;
    final repository = DriverRepository(api);

    final registered = await repository.registerPushToken(
      deviceToken: '  $deviceToken  ',
      platform: 'android',
    );

    final request = adapter.requests.single;
    expect(request.method, 'PUT');
    expect(request.path, endsWith('/notifications/push-token'));
    expect(request.headers['Authorization'], 'Bearer verified-access-token');
    final body = _decodeBody(request);
    expect(body['token'], deviceToken);
    expect(body['platform'], 'android');
    expect(registered['id'], 'b0000000-0000-4000-8000-000000000001');
    expect(registered['platform'], 'android');
  });

  test('push token removal sends the token as a query parameter', () async {
    final adapter = _PushApiAdapter();
    final api = ApiClient(accessToken: () async => 'verified-access-token');
    api.dio.httpClientAdapter = adapter;
    final repository = DriverRepository(api);

    await repository.unregisterPushToken(deviceToken: deviceToken);

    final request = adapter.requests.single;
    expect(request.method, 'DELETE');
    expect(request.path, endsWith('/notifications/push-token'));
    expect(request.queryParameters['token'], deviceToken);
    expect(request.headers['Authorization'], 'Bearer verified-access-token');
  });

  test('invalid push tokens are rejected before any request leaves the app',
      () async {
    final adapter = _PushApiAdapter();
    final api = ApiClient(accessToken: () async => 'verified-access-token');
    api.dio.httpClientAdapter = adapter;
    final repository = DriverRepository(api);

    await expectLater(
      repository.registerPushToken(
        deviceToken: 'too-short',
        platform: 'android',
      ),
      throwsArgumentError,
    );
    await expectLater(
      repository.registerPushToken(
        deviceToken: 't' * 513,
        platform: 'ios',
      ),
      throwsArgumentError,
    );
    await expectLater(
      repository.registerPushToken(
        deviceToken: deviceToken,
        platform: 'windows',
      ),
      throwsArgumentError,
    );
    await expectLater(
      repository.unregisterPushToken(deviceToken: '   '),
      throwsArgumentError,
    );
    expect(adapter.requests, isEmpty);
  });

  test('an unregistered push token surfaces the API not-found category',
      () async {
    final api = _clientReturning(404, {
      'success': false,
      'error': {
        'code': 'PUSH_TOKEN_NOT_FOUND',
        'message': 'Push token was not registered for this account',
      },
    });
    final repository = DriverRepository(api);

    await expectLater(
      repository.unregisterPushToken(deviceToken: deviceToken),
      throwsA(isA<ApiException>()
          .having((error) => error.statusCode, 'statusCode', 404)
          .having((error) => error.code, 'code', 'PUSH_TOKEN_NOT_FOUND')
          .having((error) => error.message, 'message',
              'Push token was not registered for this account')
          .having((error) => error.category, 'category', 'not_found')),
    );
  });

  test('malformed push token payload reports a safe response error', () async {
    final adapter = _PushApiAdapter(responseData: <dynamic>[]);
    final api = ApiClient(accessToken: () async => 'verified-access-token');
    api.dio.httpClientAdapter = adapter;
    final repository = DriverRepository(api);

    await expectLater(
      repository.registerPushToken(
        deviceToken: deviceToken,
        platform: 'web',
      ),
      throwsA(isA<ApiException>()
          .having((error) => error.category, 'category', 'response')
          .having((error) => error.message, 'message', contains('unexpected'))),
    );
  });

  test('notification streaming stays inert without Supabase', () async {
    final adapter = _PushApiAdapter();
    final api = ApiClient(accessToken: () async => 'verified-access-token');
    api.dio.httpClientAdapter = adapter;
    final repository = DriverRepository(api);

    expect(await repository.watchNotifications().toList(), isEmpty);
    expect(adapter.requests, isEmpty);
  });

  test('notification streaming requires a signed-in Supabase session',
      () async {
    final api = ApiClient(accessToken: () async => 'verified-access-token');
    api.dio.httpClientAdapter = _PushApiAdapter();
    final supabase = SupabaseClient(
      'https://example.supabase.co',
      'test-anon-key',
    );
    final repository = DriverRepository(api, supabase: supabase);

    expect(
      () => repository.watchNotifications(),
      throwsA(isA<StateError>()),
    );
    await supabase.dispose();
  });
}

Map<String, dynamic> _decodeBody(RequestOptions request) =>
    request.data is String
        ? jsonDecode(request.data as String) as Map<String, dynamic>
        : Map<String, dynamic>.from(request.data as Map);

ApiClient _clientReturning(int status, Map<String, dynamic> body) {
  final client = ApiClient(accessToken: () async => 'verified-access-token');
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

class _PushApiAdapter implements HttpClientAdapter {
  _PushApiAdapter({this.responseData});

  final Object? responseData;
  final requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    return ResponseBody.fromString(
      jsonEncode({
        'success': true,
        'data': responseData ??
            {
              'id': 'b0000000-0000-4000-8000-000000000001',
              'user_id': 'a0000000-0000-4000-8000-000000000001',
              'platform': 'android',
              'last_seen_at': '2026-10-30T09:00:00Z',
            },
      }),
      200,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}
