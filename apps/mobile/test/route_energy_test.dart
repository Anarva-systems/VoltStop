import 'package:flutter_test/flutter_test.dart';
import 'package:voltstop_mobile/repositories/driver_repository.dart';

void main() {
  group('estimateRouteEnergy', () {
    test('derates efficiency and marks an unreachable trip', () {
      final result = estimateRouteEnergy(
        distanceMeters: 300000,
        batteryKwh: 60,
        stateOfCharge: 80,
        efficiency: 5,
      );

      expect(result['distance_km'], 300);
      expect(result['real_world_efficiency_km_per_kwh'], 4.25);
      expect(result['estimated_consumption_kwh'], 70.59);
      expect(result['estimated_remaining_soc'], -37.65);
      expect(result['usable_range_km'], 165.75);
      expect(result['requires_charging_stop'], true);
      expect(result['unreachable_without_charge'], true);
      final window = result['optimal_charging_window'];
      expect(window['start_km'], 114.75);
      expect(window['end_km'], 153);
    });

    test('leaves a reachable trip without a charging recommendation', () {
      final result = estimateRouteEnergy(
        distanceMeters: 100000,
        batteryKwh: 40,
        stateOfCharge: 80,
        efficiency: 6,
      );

      expect(result['estimated_remaining_soc'], 30.98);
      expect(result['requires_charging_stop'], false);
      expect(result['unreachable_without_charge'], false);
      expect(result['usable_range_km'], 132.6);
    });

    test('clamps range and window to zero when starting below the buffer', () {
      final result = estimateRouteEnergy(
        distanceMeters: 10000,
        batteryKwh: 40,
        stateOfCharge: 10,
        efficiency: 6,
      );

      expect(result['usable_range_km'], 0);
      expect(result['requires_charging_stop'], true);
      expect(result['unreachable_without_charge'], false);
      final window = result['optimal_charging_window'];
      expect(window['start_km'], 0);
      expect(window['end_km'], 0);
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

    test('rejects a derate outside the usable range', () {
      expect(
        () => estimateRouteEnergy(
          distanceMeters: 1000,
          batteryKwh: 60,
          stateOfCharge: 50,
          efficiency: 5,
          derate: 0,
        ),
        throwsArgumentError,
      );
      expect(
        () => estimateRouteEnergy(
          distanceMeters: 1000,
          batteryKwh: 60,
          stateOfCharge: 50,
          efficiency: 5,
          derate: 1.2,
        ),
        throwsArgumentError,
      );
    });

    test('keeps the charging window above the safety buffer', () {
      expect(routeChargingWindowLowSocPct > routeSafetyBufferSocPct, true);
      expect(routeChargingWindowHighSocPct > routeChargingWindowLowSocPct, true);
      expect(
        () => estimateRouteEnergy(
          distanceMeters: 1000,
          batteryKwh: 60,
          stateOfCharge: 50,
          efficiency: 5,
          safetyBufferSocPct: routeChargingWindowLowSocPct,
        ),
        throwsArgumentError,
      );
    });
  });
}
