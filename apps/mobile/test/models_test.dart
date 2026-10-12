import 'package:flutter_test/flutter_test.dart';
import 'package:voltstop_mobile/models/booking.dart';
import 'package:voltstop_mobile/models/driver_profile.dart';
import 'package:voltstop_mobile/models/pitstop.dart';

void main() {
  group('DriverProfile', () {
    test('requires all vehicle and driver fields before setup is complete', () {
      const incomplete = DriverProfile(name: 'A Driver', carModel: 'EV');
      const complete = DriverProfile(
        name: 'A Driver',
        carModel: 'EV',
        batteryKwh: 60,
        efficiencyKmPerKwh: 6,
      );

      expect(incomplete.isComplete, isFalse);
      expect(complete.isComplete, isTrue);
    });

    test('maps the API profile field names', () {
      final profile = DriverProfile.fromJson({
        'id': 'driver-1',
        'name': 'A Driver',
        'car_model': 'EV',
        'battery_kwh': '60',
        'default_efficiency_km_per_kwh': '6',
        'current_soc': '73.5',
      });

      expect(profile.batteryKwh, 60);
      expect(profile.efficiencyKmPerKwh, 6);
      expect(profile.currentSoc, 73.5);
      expect(profile.toPatch()['default_efficiency_km_per_kwh'], 6);
      expect(profile.toPatch()['current_soc'], 73.5);
    });
  });

  test('pitstop model derives starting price without inventing ratings', () {
    final pitstop = Pitstop.fromJson({
      'vendor': {
        'id': 'vendor-1',
        'name': 'NH-16 Hub',
        'type': 'restaurant',
        'address': 'Rajahmundry',
      },
      'distance_km': 12.5,
      'services': [
        {'service_type': 'food', 'price_inr': '199'},
        {'service_type': 'charging', 'price_inr': '249'},
      ],
      'availability': [],
    });

    expect(pitstop.name, 'NH-16 Hub');
    expect(pitstop.distanceKm, 12.5);
    expect(pitstop.startingPrice, 199);
  });

  test('published restaurant without service rows still matches Food', () {
    final dhaba = Pitstop.fromJson({
      'vendor': {
        'id': 'village-dhaba',
        'name': 'Village Dhaba',
        'type': 'restaurant',
        'address': 'NH-16',
      },
      'distance_km': 101.84,
      'services': <dynamic>[],
      'availability': <dynamic>[],
    });

    expect(dhaba.matchesDiscoveryCategory('Food'), isTrue);
    expect(dhaba.matchesDiscoveryCategory('Hotels'), isFalse);
    expect(dhaba.matchesDiscoveryCategory('EV Charging'), isFalse);
    expect(dhaba.matchesDiscoveryCategory('All'), isTrue);
  });

  test('discovery aliases normalize to EV charging, Food, and Hotels', () {
    const charging = Pitstop(
      id: 'charger',
      name: 'Charger',
      type: 'charging_station',
      address: 'NH-16',
      distanceKm: 1,
      services: [],
      slots: [],
    );
    const foodService = Pitstop(
      id: 'food',
      name: 'Food stop',
      type: 'rest_area',
      address: 'NH-16',
      distanceKm: 1,
      services: [
        {'service_type': 'food'},
      ],
      slots: [],
    );
    const hotel = Pitstop(
      id: 'hotel',
      name: 'Hotel',
      type: 'hotel',
      address: 'NH-16',
      distanceKm: 1,
      services: [],
      slots: [],
    );

    expect(charging.matchesDiscoveryCategory('EV Charging'), isTrue);
    expect(foodService.matchesDiscoveryCategory('Food'), isTrue);
    expect(hotel.matchesDiscoveryCategory('Hotels'), isTrue);
  });

  test('booking model reads server payment order details', () {
    final booking = Booking.fromJson({
      'id': 'booking-1',
      'vendor_id': 'vendor-1',
      'slot_id': 'slot-1',
      'status': 'pending',
      'amount_inr': '249',
      'payment': {
        'order_id': 'order-1',
        'key_id': 'rzp_test_key',
        'amount_paise': 24900,
        'status': 'pending',
      },
    });

    expect(booking.orderId, 'order-1');
    expect(booking.amountPaise, 24900);
    expect(booking.status, 'pending');
  });
}
