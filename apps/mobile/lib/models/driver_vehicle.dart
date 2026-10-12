class DriverVehicle {
  const DriverVehicle({
    required this.id,
    required this.make,
    required this.model,
    required this.vehicleType,
    required this.batteryKwh,
    required this.efficiencyKmPerKwh,
    this.currentSoc,
    this.connectorCompatibility = const [],
    this.isDefault = false,
  });

  final String id;
  final String make;
  final String model;
  final String vehicleType;
  final double batteryKwh;
  final double efficiencyKmPerKwh;
  final double? currentSoc;
  final List<String> connectorCompatibility;
  final bool isDefault;

  String get displayName => '$make $model';
  bool get isComplete => batteryKwh > 0 && efficiencyKmPerKwh > 0;

  factory DriverVehicle.fromJson(Map<String, dynamic> json) => DriverVehicle(
        id: '${json['id']}',
        make: '${json['make'] ?? ''}',
        model: '${json['model'] ?? ''}',
        vehicleType: '${json['vehicle_type'] ?? 'car'}',
        batteryKwh: double.tryParse('${json['battery_kwh']}') ?? 0,
        efficiencyKmPerKwh:
            double.tryParse('${json['efficiency_km_per_kwh']}') ?? 0,
        currentSoc: json['current_soc'] == null
            ? null
            : double.tryParse('${json['current_soc']}'),
        connectorCompatibility:
            (json['connector_compatibility'] as List? ?? const [])
                .map((value) => '$value')
                .toList(growable: false),
        isDefault: json['is_default'] == true,
      );
}
