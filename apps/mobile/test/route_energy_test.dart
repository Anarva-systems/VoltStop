import 'package:flutter_test/flutter_test.dart';
import 'package:voltstop_mobile/repositories/driver_repository.dart';

void main() {
  group('estimateRouteEnergy', () {
    test('computes road distance, consumption, and remaining state of charge',
        () {
      final result = estimateRouteEnergy(
        distanceMeters: 300000,
        batteryKwh: 60,
        stateOfCharge: 80,
        efficiency: 5,
      );

      expect(result['distance_km'], 300);
      expect(result['estimated_consumption_kwh'], 60);
      expect(result['estimated_remaining_soc'], -20);
    });

    test('rejects invalid battery, charge, efficiency, and distance inputs',
        () {
      expect(
        () => estimateRouteEnergy(
          distanceMeters: 1000,
          batteryKwh: 0,
          stateOfCharge: 50,
          efficiency: 5,
        ),
        throwsArgumentError,
      );
      expect(
        () => estimateRouteEnergy(
          distanceMeters: 1000,
          batteryKwh: 60,
          stateOfCharge: 101,
          efficiency: 5,
        ),
        throwsArgumentError,
      );
      expect(
        () => estimateRouteEnergy(
          distanceMeters: 1000,
          batteryKwh: 60,
          stateOfCharge: 50,
          efficiency: 21,
        ),
        throwsArgumentError,
      );
      expect(
        () => estimateRouteEnergy(
          distanceMeters: 0,
          batteryKwh: 60,
          stateOfCharge: 50,
          efficiency: 5,
        ),
        throwsArgumentError,
      );
    });
  });
}
