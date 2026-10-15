import 'dart:async';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../core/config/app_config.dart';
import '../core/services/api_client.dart';
import '../models/booking.dart';
import '../models/driver_profile.dart';
import '../models/driver_trip.dart';
import '../models/driver_vehicle.dart';
import '../models/pitstop.dart';

class DriverRepository {
  DriverRepository(this._api, {SupabaseClient? supabase})
      : _supabase = supabase;

  final ApiClient _api;
  final SupabaseClient? _supabase;

  Future<void> checkApiReadiness() => _api.checkReadiness();

  SupabaseClient get _database {
    final client = _supabase;
    if (client == null) {
      throw StateError('Supabase is not configured for driver data.');
    }
    return client;
  }

  String get _userId {
    final userId = _database.auth.currentUser?.id;
    if (userId == null) throw StateError('Sign in to access driver data.');
    return userId;
  }

  Future<DriverProfile> profile() async {
    // The authenticated API verifies the Supabase token and synchronizes a
    // profile row before reading it. This handles first sign-ins even when the
    // Auth user's profile trigger was missing or delayed.
    final result = await _api.get('/profile');
    if (result is! Map) {
      throw const ApiException(
        'VoltStop returned an unexpected driver profile response. Retry or contact support.',
        category: 'response',
      );
    }
    return DriverProfile.fromJson(Map<String, dynamic>.from(result));
  }

  Future<DriverProfile> saveProfile(DriverProfile profile) async {
    final userId = _supabase?.auth.currentUser?.id;
    if (userId != null && profile.id != null && profile.id != userId) {
      throw StateError('A driver can only update their own profile.');
    }
    return DriverProfile.fromJson(
      Map<String, dynamic>.from(
        await _api.patch('/profile', data: profile.toPatch()) as Map,
      ),
    );
  }

  Future<Map<String, dynamic>> planRoute({
    required String origin,
    required String destination,
    required double batteryKwh,
    required double stateOfCharge,
    required double efficiency,
    bool persist = true,
    DateTime? departureAt,
  }) async {
    _validateRouteInputs(batteryKwh, stateOfCharge, efficiency);
    return Map<String, dynamic>.from(await _api.post(
      '/routes/plan',
      data: {
        'origin': origin,
        'destination': destination,
        'battery_kwh': batteryKwh,
        'current_soc': stateOfCharge,
        'efficiency_km_per_kwh': efficiency,
        'persist': persist,
        if (departureAt != null)
          'departure_at': departureAt.toUtc().toIso8601String(),
      },
    ) as Map);
  }

  Future<List<DriverTrip>> driverTrips({String bucket = 'upcoming'}) async {
    final result = await _api.get('/routes/trips', query: {'bucket': bucket});
    if (result is! List) {
      throw const FormatException('Trips response is invalid.');
    }
    return result
        .whereType<Map>()
        .map((item) => DriverTrip.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }

  Future<List<Map<String, dynamic>>> discoverDriverTrips({
    String? origin,
    String? destination,
    DateTime? departureOn,
  }) async {
    final query = <String, dynamic>{};
    if (origin != null && origin.isNotEmpty) query['origin'] = origin;
    if (destination != null && destination.isNotEmpty) {
      query['destination'] = destination;
    }
    if (departureOn != null) {
      final localStart = DateTime(
        departureOn.year,
        departureOn.month,
        departureOn.day,
      );
      final localEnd = DateTime(
        departureOn.year,
        departureOn.month,
        departureOn.day + 1,
      );
      query['departure_from'] = localStart.toUtc().toIso8601String();
      query['departure_before'] = localEnd.toUtc().toIso8601String();
    }
    final result = await _api.get('/routes/trips/discover', query: query);
    if (result is! List) {
      throw const FormatException('Trip discovery response is invalid.');
    }
    return result
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
  }

  Future<DriverTrip> driverTrip(String tripId) async => DriverTrip.fromJson(
        Map<String, dynamic>.from(
            await _api.get('/routes/trips/$tripId') as Map),
      );

  Future<DriverTrip> createDriverTrip({
    required String origin,
    required String destination,
    required DateTime departureAt,
    DateTime? estimatedArrivalAt,
    required String vehicleId,
    double? currentSoc,
    required int availableSeats,
    String? notes,
    required bool isDiscoverable,
    required String idempotencyKey,
  }) async =>
      DriverTrip.fromJson(Map<String, dynamic>.from(await _api.post(
        '/routes/trips',
        data: _driverTripPayload(
          origin: origin,
          destination: destination,
          departureAt: departureAt,
          estimatedArrivalAt: estimatedArrivalAt,
          vehicleId: vehicleId,
          currentSoc: currentSoc,
          availableSeats: availableSeats,
          notes: notes,
          isDiscoverable: isDiscoverable,
        ),
        headers: {'Idempotency-Key': idempotencyKey},
      ) as Map));

  Future<DriverTrip> updateDriverTrip({
    required String tripId,
    required String origin,
    required String destination,
    required DateTime departureAt,
    DateTime? estimatedArrivalAt,
    required String vehicleId,
    double? currentSoc,
    required int availableSeats,
    String? notes,
    required bool isDiscoverable,
  }) async =>
      DriverTrip.fromJson(Map<String, dynamic>.from(await _api.put(
        '/routes/trips/$tripId',
        data: _driverTripPayload(
          origin: origin,
          destination: destination,
          departureAt: departureAt,
          estimatedArrivalAt: estimatedArrivalAt,
          vehicleId: vehicleId,
          currentSoc: currentSoc,
          availableSeats: availableSeats,
          notes: notes,
          isDiscoverable: isDiscoverable,
        ),
      ) as Map));

  Future<DriverTrip> transitionDriverTrip(String tripId, String action) async {
    if (!const {'start', 'complete', 'cancel'}.contains(action)) {
      throw ArgumentError.value(action, 'action');
    }
    return DriverTrip.fromJson(Map<String, dynamic>.from(await _api.post(
      '/routes/trips/$tripId/$action',
    ) as Map));
  }

  Map<String, dynamic> _driverTripPayload({
    required String origin,
    required String destination,
    required DateTime departureAt,
    DateTime? estimatedArrivalAt,
    required String vehicleId,
    double? currentSoc,
    required int availableSeats,
    String? notes,
    required bool isDiscoverable,
  }) =>
      {
        'origin': origin,
        'destination': destination,
        'departure_at': departureAt.toUtc().toIso8601String(),
        'estimated_arrival_at': estimatedArrivalAt?.toUtc().toIso8601String(),
        'vehicle_id': vehicleId,
        'current_soc': currentSoc,
        'available_seats': availableSeats,
        'notes': notes?.trim().isEmpty == true ? null : notes?.trim(),
        'is_discoverable': isDiscoverable,
      };

  Future<List<DriverVehicle>> vehicles() async {
    final result = await _api.get('/vehicles');
    if (result is! List)
      throw const FormatException('Vehicles response is invalid.');
    return result
        .whereType<Map>()
        .map((item) => DriverVehicle.fromJson(
              Map<String, dynamic>.from(item),
            ))
        .toList();
  }

  Future<DriverVehicle> createVehicle({
    required String make,
    required String model,
    required String vehicleType,
    required double batteryKwh,
    required double efficiencyKmPerKwh,
    double? currentSoc,
    List<String> connectorCompatibility = const [],
    bool isDefault = false,
  }) async {
    final key = 'mobile-${DateTime.now().microsecondsSinceEpoch}';
    return DriverVehicle.fromJson(Map<String, dynamic>.from(await _api.post(
      '/vehicles',
      data: {
        'make': make.trim(),
        'model': model.trim(),
        'vehicle_type': vehicleType,
        'battery_kwh': batteryKwh,
        'efficiency_km_per_kwh': efficiencyKmPerKwh,
        'current_soc': currentSoc,
        'connector_compatibility': connectorCompatibility,
        'is_default': isDefault,
      },
      headers: {'Idempotency-Key': key},
    ) as Map));
  }

  Future<DriverVehicle> updateVehicle(
          String id, Map<String, dynamic> changes) async =>
      DriverVehicle.fromJson(Map<String, dynamic>.from(await _api.patch(
        '/vehicles/$id',
        data: changes,
      ) as Map));

  Future<DriverVehicle> selectDefaultVehicle(String id) async =>
      DriverVehicle.fromJson(Map<String, dynamic>.from(await _api.post(
        '/vehicles/$id/default',
      ) as Map));

  Future<void> deleteVehicle(String id) async {
    await _api.delete('/vehicles/$id');
  }

  Future<List<Pitstop>> nearbyPitstops({
    double lat = AppConfig.discoveryFallbackLat,
    double lng = AppConfig.discoveryFallbackLng,
    double radiusKm = 200,
  }) async {
    final result = await _api.get(
      '/vendors/nearby',
      query: {'lat': lat, 'lng': lng, 'radius_km': radiusKm},
    );
    if (result is! List) {
      throw const FormatException('Nearby places response is invalid.');
    }
    return result
        .whereType<Map>()
        .map((item) => Pitstop.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<Pitstop> pitstop(String id) async {
    final result = await _api.get('/vendors/$id');
    if (result is! Map) {
      throw const FormatException('Place details response is invalid.');
    }
    return Pitstop.fromJson(Map<String, dynamic>.from(result));
  }

  Future<List<Map<String, dynamic>>> slots(String vendorId) async {
    final result = await _api.get('/vendors/$vendorId/slots');
    if (result is! List) {
      throw const FormatException('Charging slots response is invalid.');
    }
    return result
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  Future<Map<String, dynamic>> lockSlot(String slotId) async =>
      Map<String, dynamic>.from(
        await _api.post('/bookings/lock', data: {'slot_id': slotId}) as Map,
      );

  Future<Booking> createBooking(String slotId, String lockToken) async =>
      Booking.fromJson(
        Map<String, dynamic>.from(
          await _api.post(
            '/bookings',
            data: {'slot_id': slotId, 'lock_token': lockToken},
          ) as Map,
        ),
      );

  Future<Map<String, dynamic>> verifyRazorpayCheckout({
    required String orderId,
    required String paymentId,
    required String signature,
  }) async =>
      Map<String, dynamic>.from(
        await _api.post(
          '/payments/razorpay/verify',
          data: {
            'order_id': orderId,
            'payment_id': paymentId,
            'signature': signature,
          },
        ) as Map,
      );

  Future<List<Map<String, dynamic>>> hotelRooms({
    required String vendorId,
    required DateTime checkIn,
    required DateTime checkOut,
    required int guests,
    int rooms = 1,
  }) async {
    final result = await _api.get(
      '/hotels/rooms',
      query: {
        'vendor_id': vendorId,
        'check_in': checkIn.toIso8601String().split('T').first,
        'check_out': checkOut.toIso8601String().split('T').first,
        'guests': guests,
        'rooms': rooms,
      },
    );
    if (result is! List)
      throw const FormatException('Hotel rooms response is invalid.');
    return result
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  Future<Map<String, dynamic>> createHotelReservation({
    required String roomTypeId,
    required DateTime checkIn,
    required DateTime checkOut,
    required int guests,
    int rooms = 1,
    required String expectedAmountInr,
    required String idempotencyKey,
  }) async =>
      Map<String, dynamic>.from(
        await _api.post(
          '/hotels/reservations',
          data: {
            'room_type_id': roomTypeId,
            'check_in': checkIn.toIso8601String().split('T').first,
            'check_out': checkOut.toIso8601String().split('T').first,
            'guests': guests,
            'rooms': rooms,
            'expected_amount_inr': expectedAmountInr,
          },
          headers: {'Idempotency-Key': idempotencyKey},
        ) as Map,
      );

  Future<Map<String, dynamic>> hotelQuote({
    required String roomTypeId,
    required DateTime checkIn,
    required DateTime checkOut,
    required int guests,
    int rooms = 1,
  }) async =>
      Map<String, dynamic>.from(
        await _api.post(
          '/hotels/quotes',
          data: {
            'room_type_id': roomTypeId,
            'check_in': checkIn.toIso8601String().split('T').first,
            'check_out': checkOut.toIso8601String().split('T').first,
            'guests': guests,
            'rooms': rooms,
          },
        ) as Map,
      );

  Future<Map<String, dynamic>> hotelReservation(String id) async =>
      Map<String, dynamic>.from(
        await _api.get('/hotels/reservations/$id') as Map,
      );

  Future<List<Map<String, dynamic>>> hotelReservations() async {
    final result = await _api.get('/hotels/reservations');
    if (result is! List)
      throw const FormatException('Hotel reservations response is invalid.');
    return result
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  Future<Map<String, dynamic>> cancelHotelReservation(String id) async =>
      Map<String, dynamic>.from(
        await _api.post('/hotels/reservations/$id/cancel') as Map,
      );

  Future<Map<String, dynamic>> restaurantMenu(String vendorId) async =>
      Map<String, dynamic>.from(
        await _api.get('/restaurants/$vendorId/menu') as Map,
      );

  Future<Map<String, dynamic>> createRestaurantOrder({
    required String vendorId,
    required List<Map<String, dynamic>> items,
    required String idempotencyKey,
  }) async =>
      Map<String, dynamic>.from(
        await _api.post(
          '/restaurants/orders',
          data: {
            'vendor_id': vendorId,
            'fulfillment_method': 'pickup',
            'items': items,
          },
          headers: {'Idempotency-Key': idempotencyKey},
        ) as Map,
      );

  Future<List<Map<String, dynamic>>> restaurantOrders() async {
    final result = await _api.get('/restaurants/orders');
    if (result is! List)
      throw const FormatException('Restaurant orders response is invalid.');
    return result
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  Future<List<Booking>> bookings() => _loadBookings();

  /// Realtime updates are owner-scoped by both the PostgREST filter and RLS.
  /// Consumers should keep a low-frequency refresh as a network/publication
  /// recovery path.
  Stream<void> watchBookings() {
    final client = _supabase;
    if (client == null) return const Stream<void>.empty();
    final userId = _userId;
    return client
        .from('bookings')
        .stream(primaryKey: ['id'])
        .eq('user_id', userId)
        .map<void>((_) {});
  }

  Stream<void> watchBooking(String bookingId) {
    final client = _supabase;
    if (client == null) return const Stream<void>.empty();
    final userId = _userId;
    return client
        .from('bookings')
        .stream(primaryKey: ['id'])
        .eq('id', bookingId)
        .eq('user_id', userId)
        .map<void>((_) {});
  }

  Stream<void> watchPitstopChanges(String vendorId) {
    final client = _supabase;
    if (client == null) return const Stream<void>.empty();
    final controller = StreamController<void>();
    final subscriptions = <StreamSubscription<dynamic>>[];
    void forward(Object? _) {
      if (!controller.isClosed) controller.add(null);
    }

    void reportError(Object error, [StackTrace? stackTrace]) {
      if (!controller.isClosed) {
        controller.addError(error, stackTrace ?? StackTrace.current);
      }
    }

    subscriptions.add(
      client
          .from('vendors')
          .stream(primaryKey: ['id'])
          .eq('id', vendorId)
          .listen(forward, onError: reportError),
    );
    subscriptions.add(
      client
          .from('vendor_services')
          .stream(primaryKey: ['id'])
          .eq('vendor_id', vendorId)
          .listen(forward, onError: reportError),
    );
    subscriptions.add(
      client
          .from('charging_slots')
          .stream(primaryKey: ['id'])
          .eq('vendor_id', vendorId)
          .listen(forward, onError: reportError),
    );

    controller.onCancel = () async {
      for (final subscription in subscriptions) {
        await subscription.cancel();
      }
    };
    return controller.stream;
  }

  Stream<void> watchPitstopDirectoryChanges() {
    final client = _supabase;
    if (client == null) return const Stream<void>.empty();
    final topic =
        'driver-catalog:${_userId}:${DateTime.now().microsecondsSinceEpoch}';
    final channel = client.channel(topic);
    final controller = StreamController<void>();
    void changed(dynamic _) {
      if (!controller.isClosed) controller.add(null);
    }

    for (final table in ['vendors', 'vendor_services', 'charging_slots']) {
      channel.onPostgresChanges(
        event: PostgresChangeEvent.all,
        schema: 'public',
        table: table,
        callback: changed,
      );
    }
    controller.onListen = () {
      channel.subscribe((status, [error]) {
        if (status == RealtimeSubscribeStatus.channelError ||
            status == RealtimeSubscribeStatus.timedOut) {
          if (!controller.isClosed) {
            controller.addError(
              error ?? StateError('Pitstop live updates are unavailable.'),
              StackTrace.current,
            );
          }
        }
      });
    };
    controller.onCancel = () async {
      await client.removeChannel(channel);
    };
    return controller.stream;
  }

  Future<Booking> booking(String id) async {
    final rows = await _loadBookings(bookingId: id);
    if (rows.isEmpty) throw StateError('Booking was not found.');
    return rows.first;
  }

  Future<List<Booking>> _loadBookings({String? bookingId}) async {
    if (bookingId != null) {
      final result = await _api.get('/bookings/$bookingId');
      if (result is! Map) {
        throw const FormatException('Booking response is invalid.');
      }
      return [Booking.fromJson(Map<String, dynamic>.from(result))];
    }
    final result = await _api.get('/bookings', query: {'limit': 100});
    if (result is! List) {
      throw const FormatException('Bookings response is invalid.');
    }
    return result
        .whereType<Map>()
        .map((item) => Booking.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<Booking> cancelBooking(String id) async => Booking.fromJson(
        Map<String, dynamic>.from(
            await _api.post('/bookings/$id/cancel') as Map),
      );

  Future<List<Map<String, dynamic>>> disputes() async {
    final result = await _api.get('/disputes');
    if (result is List) {
      return result.whereType<Map>().map(Map<String, dynamic>.from).toList();
    }
    if (result is Map && result['items'] is List) {
      return (result['items'] as List)
          .whereType<Map>()
          .map(Map<String, dynamic>.from)
          .toList();
    }
    throw const FormatException('Dispute response has an unexpected format.');
  }

  Future<Map<String, dynamic>> dispute(String id) async =>
      Map<String, dynamic>.from(await _api.get('/disputes/$id') as Map);

  Future<Map<String, dynamic>> createDispute({
    required String bookingId,
    required String reason,
    required String description,
    required String idempotencyKey,
  }) async =>
      Map<String, dynamic>.from(
        await _api.post(
          '/disputes',
          data: {
            'booking_id': bookingId,
            'reason': reason,
            'description': description,
          },
          headers: {'Idempotency-Key': idempotencyKey},
        ) as Map,
      );

  Future<Map<String, dynamic>> addDisputeMessage({
    required String disputeId,
    required String message,
    required String idempotencyKey,
  }) async =>
      Map<String, dynamic>.from(
        await _api.post(
          '/disputes/$disputeId/messages',
          data: {'message': message},
          headers: {'Idempotency-Key': idempotencyKey},
        ) as Map,
      );
}

Map<String, double> estimateRouteEnergy({
  required int distanceMeters,
  required double batteryKwh,
  required double stateOfCharge,
  required double efficiency,
}) {
  _validateRouteInputs(batteryKwh, stateOfCharge, efficiency);
  if (distanceMeters <= 0)
    throw ArgumentError.value(distanceMeters, 'distanceMeters');
  final distanceKm = distanceMeters / 1000;
  final consumption = distanceKm / efficiency;
  final remainingSoc = stateOfCharge - (consumption / batteryKwh * 100);
  return {
    'distance_km': double.parse(distanceKm.toStringAsFixed(2)),
    'estimated_consumption_kwh': double.parse(consumption.toStringAsFixed(2)),
    'estimated_remaining_soc': double.parse(remainingSoc.toStringAsFixed(2)),
  };
}

void _validateRouteInputs(
  double batteryKwh,
  double stateOfCharge,
  double efficiency,
) {
  if (!batteryKwh.isFinite || batteryKwh <= 0 || batteryKwh > 500) {
    throw ArgumentError.value(batteryKwh, 'batteryKwh');
  }
  if (!stateOfCharge.isFinite || stateOfCharge < 0 || stateOfCharge > 100) {
    throw ArgumentError.value(stateOfCharge, 'stateOfCharge');
  }
  if (!efficiency.isFinite || efficiency <= 0 || efficiency > 20) {
    throw ArgumentError.value(efficiency, 'efficiency');
  }
}
