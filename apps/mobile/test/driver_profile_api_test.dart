import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:supabase_flutter/supabase_flutter.dart' show SupabaseClient;
import 'package:voltstop_mobile/core/services/api_client.dart';
import 'package:voltstop_mobile/models/driver_profile.dart';
import 'package:voltstop_mobile/repositories/driver_repository.dart';

void main() {
  test('driver profile load uses the authenticated backend endpoint', () async {
    final adapter = _ProfileApiAdapter();
    final api = ApiClient(accessToken: () async => 'verified-access-token');
    api.dio.httpClientAdapter = adapter;
    final repository = DriverRepository(api);

    final profile = await repository.profile();

    expect(profile.id, 'a0000000-0000-4000-8000-000000000001');
    expect(profile.phone, '+919876543210');
    expect(adapter.requests, hasLength(1));
    expect(adapter.requests.single.method, 'GET');
    expect(adapter.requests.single.path, endsWith('/profile'));
    expect(
      adapter.requests.single.headers['Authorization'],
      'Bearer verified-access-token',
    );
  });

  test('malformed profile payload reports a safe response error', () async {
    final adapter = _ProfileApiAdapter(responseData: <dynamic>[]);
    final api = ApiClient(accessToken: () async => 'verified-access-token');
    api.dio.httpClientAdapter = adapter;
    final repository = DriverRepository(api);

    await expectLater(
      repository.profile(),
      throwsA(isA<ApiException>()
          .having((error) => error.category, 'category', 'response')
          .having((error) => error.message, 'message', contains('unexpected'))),
    );
  });

  test('driver profile save sends changes to the authenticated API', () async {
    final adapter = _ProfileApiAdapter();
    final api = ApiClient(accessToken: () async => 'verified-access-token');
    api.dio.httpClientAdapter = adapter;
    final repository = DriverRepository(api);

    await repository.saveProfile(
      const DriverProfile(
        name: 'Test Driver',
        carModel: 'Test EV',
        batteryKwh: 60,
        efficiencyKmPerKwh: 6.2,
      ),
    );

    final request = adapter.requests.single;
    expect(request.method, 'PATCH');
    expect(request.path, endsWith('/profile'));
    expect(request.headers['Authorization'], 'Bearer verified-access-token');
    final body = request.data is String
        ? jsonDecode(request.data as String) as Map<String, dynamic>
        : Map<String, dynamic>.from(request.data as Map);
    expect(body['name'], 'Test Driver');
    expect(body['car_model'], 'Test EV');
    expect(body['battery_kwh'], 60);
    expect(body['default_efficiency_km_per_kwh'], 6.2);
  });

  test('nearby discovery uses FastAPI even when Supabase is configured',
      () async {
    final adapter = _DirectoryApiAdapter();
    final api = ApiClient(accessToken: () async => 'verified-access-token');
    api.dio.httpClientAdapter = adapter;
    final supabase = SupabaseClient(
      'https://example.supabase.co',
      'test-anon-key',
    );
    final repository = DriverRepository(api, supabase: supabase);

    final results = await repository.nearbyPitstops(
      lat: 17.7,
      lng: 83.3,
      radiusKm: 75,
    );

    expect(results, isEmpty);
    expect(adapter.requests, hasLength(1));
    final request = adapter.requests.single;
    expect(request.path, endsWith('/vendors/nearby'));
    expect(request.queryParameters['lat'], 17.7);
    expect(request.queryParameters['lng'], 83.3);
    expect(request.queryParameters['radius_km'], 75);
    expect(request.headers['Authorization'], 'Bearer verified-access-token');
    await supabase.dispose();
  });

  test('booking history uses authenticated FastAPI instead of PostgREST',
      () async {
    final adapter = _DirectoryApiAdapter();
    final api = ApiClient(accessToken: () async => 'verified-access-token');
    api.dio.httpClientAdapter = adapter;
    final supabase = SupabaseClient(
      'https://example.supabase.co',
      'test-anon-key',
    );
    final repository = DriverRepository(api, supabase: supabase);

    final bookings = await repository.bookings();

    expect(bookings, isEmpty);
    expect(adapter.requests, hasLength(1));
    final request = adapter.requests.single;
    expect(request.path, endsWith('/bookings'));
    expect(request.queryParameters['limit'], 100);
    expect(request.headers['Authorization'], 'Bearer verified-access-token');
    await supabase.dispose();
  });

  test('route planning uses the authenticated API with configured Supabase',
      () async {
    final adapter = _RouteApiAdapter();
    final api = ApiClient(accessToken: () async => 'verified-access-token');
    api.dio.httpClientAdapter = adapter;
    final supabase = SupabaseClient(
      'https://example.supabase.co',
      'test-anon-key',
    );
    final repository = DriverRepository(api, supabase: supabase);

    final route = await repository.planRoute(
      origin: 'Srikakulam',
      destination: 'Vijayawada',
      batteryKwh: 60,
      stateOfCharge: 75,
      efficiency: 6.2,
      persist: false,
    );

    expect(route['distance_km'], 447.34);
    expect(route['estimated_duration_seconds'], 25200);
    expect(adapter.requests, hasLength(1));
    final request = adapter.requests.single;
    expect(request.path, endsWith('/routes/plan'));
    expect(request.headers['Authorization'], 'Bearer verified-access-token');
    final body = request.data is String
        ? jsonDecode(request.data as String) as Map<String, dynamic>
        : Map<String, dynamic>.from(request.data as Map);
    expect(body['battery_kwh'], 60);
    expect(body['current_soc'], 75);
    expect(body['efficiency_km_per_kwh'], 6.2);
    expect(body['persist'], isFalse);
    await supabase.dispose();
  });

  test('route planner sends the selected departure as UTC ISO-8601', () async {
    final adapter = _RouteApiAdapter();
    final api = ApiClient(accessToken: () async => 'verified-access-token');
    api.dio.httpClientAdapter = adapter;
    final repository = DriverRepository(api);
    final departure = DateTime.utc(2027, 1, 2, 3, 4);

    await repository.planRoute(
      origin: 'Srikakulam',
      destination: 'Vijayawada',
      batteryKwh: 60,
      stateOfCharge: 75,
      efficiency: 6.2,
      persist: true,
      departureAt: departure,
    );

    final body = adapter.requests.single.data is String
        ? jsonDecode(adapter.requests.single.data as String)
            as Map<String, dynamic>
        : Map<String, dynamic>.from(adapter.requests.single.data as Map);
    expect(DateTime.parse(body['departure_at'] as String).toUtc(), departure);
  });

  test('nearby discovery defaults to the NH-16 pilot start location', () async {
    final adapter = _DirectoryApiAdapter();
    final api = ApiClient(accessToken: () async => 'verified-access-token');
    api.dio.httpClientAdapter = adapter;
    final repository = DriverRepository(api);

    await repository.nearbyPitstops();

    final request = adapter.requests.single;
    expect(request.path, endsWith('/vendors/nearby'));
    expect(request.queryParameters['lat'], 18.2969);
    expect(request.queryParameters['lng'], 83.8968);
    expect(request.queryParameters['radius_km'], 200);
  });

  test('route request validates charge and retries a failed API request',
      () async {
    final adapter = _RouteApiAdapter(failFirst: true);
    final api = ApiClient(accessToken: () async => 'verified-access-token');
    api.dio.httpClientAdapter = adapter;
    final repository = DriverRepository(api);

    await expectLater(
      repository.planRoute(
        origin: 'Srikakulam',
        destination: 'Vijayawada',
        batteryKwh: 60,
        stateOfCharge: 101,
        efficiency: 6,
      ),
      throwsArgumentError,
    );
    expect(adapter.requests, isEmpty);

    await expectLater(
      repository.planRoute(
        origin: 'Srikakulam',
        destination: 'Vijayawada',
        batteryKwh: 60,
        stateOfCharge: 75,
        efficiency: 6,
        persist: false,
      ),
      throwsA(isA<ApiException>()),
    );
    final retry = await repository.planRoute(
      origin: 'Srikakulam',
      destination: 'Vijayawada',
      batteryKwh: 60,
      stateOfCharge: 75,
      efficiency: 6,
      persist: false,
    );

    expect(retry['distance_km'], 447.34);
    expect(adapter.requests, hasLength(2));
  });
}

class _ProfileApiAdapter implements HttpClientAdapter {
  _ProfileApiAdapter({this.responseData});

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
              'id': 'a0000000-0000-4000-8000-000000000001',
              'phone': '+919876543210',
              'name': 'Test Driver',
              'car_model': 'Test EV',
              'battery_kwh': 60,
              'default_efficiency_km_per_kwh': 6.2,
              'current_soc': 75,
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

class _DirectoryApiAdapter implements HttpClientAdapter {
  final requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    return ResponseBody.fromString(
      jsonEncode({'success': true, 'data': <dynamic>[]}),
      200,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

class _RouteApiAdapter implements HttpClientAdapter {
  _RouteApiAdapter({this.failFirst = false});

  final bool failFirst;
  final requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    if (failFirst && requests.length == 1) {
      return ResponseBody.fromString(
        jsonEncode({
          'success': false,
          'error': {'message': 'OpenStreetMap Routes could not be reached'},
        }),
        503,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      );
    }
    return ResponseBody.fromString(
      jsonEncode({
        'success': true,
        'data': {
          'distance_km': 447.34,
          'estimated_duration_seconds': 25200,
          'estimated_consumption_kwh': 72.15,
          'estimated_remaining_soc': -45.25,
          'route_coordinates': [
            [83.8968, 18.2969],
            [80.648, 16.5062],
          ],
          'recommended_pitstops': <dynamic>[],
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
