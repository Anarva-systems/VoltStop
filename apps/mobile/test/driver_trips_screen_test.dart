import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voltstop_mobile/controllers/app_controller.dart';
import 'package:voltstop_mobile/core/services/api_client.dart';
import 'package:voltstop_mobile/features/driver/views/upcoming_trips_screen.dart';
import 'package:voltstop_mobile/models/driver_trip.dart';
import 'package:voltstop_mobile/repositories/auth_repository.dart';
import 'package:voltstop_mobile/repositories/driver_repository.dart';

class _TripsRepository extends DriverRepository {
  _TripsRepository() : super(ApiClient(accessToken: () async => null));

  @override
  Future<List<DriverTrip>> driverTrips({String bucket = 'upcoming'}) async =>
      [];

  @override
  Future<List<Map<String, dynamic>>> discoverDriverTrips({
    String? origin,
    String? destination,
    DateTime? departureOn,
  }) async =>
      [];
}

void main() {
  testWidgets('Trips navigation exposes owned drives and browse-only discovery',
      (tester) async {
    final app = AppController(
      auth: AuthRepository(),
      driverRepository: _TripsRepository(),
    );

    await tester.pumpWidget(MaterialApp(
      home: DriverTripsScreen(app: app, reservations: const SizedBox.shrink()),
    ));
    await tester.pumpAndSettle();

    expect(find.text('My drives'), findsOneWidget);
    expect(find.text('Discover'), findsOneWidget);
    expect(find.text('Reservations'), findsOneWidget);
    expect(find.text('No upcoming drives yet'), findsOneWidget);

    await tester.tap(find.text('Discover'));
    await tester.pumpAndSettle();
    expect(find.text('No listed trips match these filters.'), findsOneWidget);
    expect(find.textContaining('does not book seats'), findsOneWidget);
  });
}
