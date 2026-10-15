import 'package:flutter_test/flutter_test.dart';
import 'package:voltstop_mobile/models/driver_trip.dart';

void main() {
  test('trip model parses lifecycle, local times, and route suggestions', () {
    final departure = DateTime.parse('2026-11-12T14:30:00+00:00');
    final trip = DriverTrip.fromJson({
      'id': 'trip-1',
      'origin': 'Srikakulam, Andhra Pradesh, India',
      'destination': 'Vijayawada, Andhra Pradesh, India',
      'departure_at': departure.toIso8601String(),
      'estimated_arrival_at': '2026-11-12T20:30:00+00:00',
      'vehicle_id': 'vehicle-1',
      'vehicle_make': 'Tata',
      'vehicle_model': 'Nexon EV',
      'available_seats': 3,
      'notes': 'Private note',
      'is_discoverable': true,
      'status': 'scheduled',
      'route_plan': {
        'distance_meters': 447000,
        'estimated_consumption_kwh': 22.4,
      },
      'recommended_pitstops': [
        {
          'vendor': {'name': 'NH-16 station'},
          'distance_km': 12.5,
        },
      ],
    });

    expect(trip.id, 'trip-1');
    expect(trip.vehicleName, 'Tata Nexon EV');
    expect(trip.departureAt, departure.toLocal());
    expect(trip.estimatedArrivalAt, isNotNull);
    expect(trip.availableSeats, 3);
    expect(trip.isDiscoverable, isTrue);
    expect(trip.status, 'scheduled');
    expect(trip.routePlan?['distance_meters'], 447000);
    expect(trip.recommendedPitstops.single['distance_km'], 12.5);
  });

  test('trip model tolerates an absent route estimate', () {
    final trip = DriverTrip.fromJson({
      'id': 'trip-2',
      'origin': 'Srikakulam',
      'destination': 'Vijayawada',
      'departure_at': '2026-11-12T14:30:00Z',
      'vehicle_make': 'Tata',
      'vehicle_model': 'Nexon EV',
      'available_seats': 2,
      'status': 'cancelled',
    });

    expect(trip.routePlan, isNull);
    expect(trip.recommendedPitstops, isEmpty);
    expect(trip.status, 'cancelled');
  });
}
