import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voltstop_mobile/controllers/app_controller.dart';
import 'package:voltstop_mobile/core/services/api_client.dart';
import 'package:voltstop_mobile/core/theme/app_theme.dart';
import 'package:voltstop_mobile/features/driver/views/driver_screens.dart';
import 'package:voltstop_mobile/models/booking.dart';
import 'package:voltstop_mobile/repositories/auth_repository.dart';
import 'package:voltstop_mobile/repositories/driver_repository.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('trip history reloads after a booking Realtime event',
      (tester) async {
    final repository = _MutableBookingRepository();
    addTearDown(repository.dispose);
    final app = AppController(
      auth: AuthRepository(),
      driverRepository: repository,
    );

    await tester.pumpWidget(MaterialApp(
      theme: buildVoltStopTheme(),
      home: Scaffold(body: BookingsScreen(app: app)),
    ));
    await tester.pumpAndSettle();
    expect(find.textContaining('No upcoming bookings'), findsOneWidget);

    repository.rows = const [
      Booking(
        id: 'booking-live-1',
        status: 'confirmed',
        amountInr: 249,
        slotId: 'slot-1',
        vendorId: 'vendor-1',
        vendorName: 'Realtime Charge Hub',
      ),
    ];
    repository.changes.add(null);
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pumpAndSettle();

    expect(find.text('Realtime Charge Hub'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

class _MutableBookingRepository extends DriverRepository {
  _MutableBookingRepository() : super(ApiClient(accessToken: () async => null));

  final StreamController<void> changes = StreamController<void>.broadcast();
  List<Booking> rows = const [];

  @override
  Future<List<Booking>> bookings() async => rows;

  @override
  Future<List<Map<String, dynamic>>> hotelReservations() async => [];

  @override
  Stream<void> watchBookings() => changes.stream;

  Future<void> dispose() => changes.close();
}
