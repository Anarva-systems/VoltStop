import 'package:flutter_test/flutter_test.dart';
import 'package:voltstop_mobile/models/driver_vehicle.dart';

void main() {
  test('vehicle model parses persisted default and vehicle-specific charge',
      () {
    final vehicle = DriverVehicle.fromJson({
      'id': 'vehicle-1',
      'make': 'Tata',
      'model': 'Nexon EV',
      'vehicle_type': 'suv',
      'battery_kwh': '40.50',
      'efficiency_km_per_kwh': '6.10',
      'current_soc': '63',
      'connector_compatibility': ['CCS2'],
      'is_default': true,
    });
    expect(vehicle.displayName, 'Tata Nexon EV');
    expect(vehicle.batteryKwh, 40.5);
    expect(vehicle.currentSoc, 63);
    expect(vehicle.connectorCompatibility, ['CCS2']);
    expect(vehicle.isDefault, isTrue);
  });
}
