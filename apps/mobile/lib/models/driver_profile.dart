class DriverProfile {
  const DriverProfile({
    this.id,
    this.phone,
    this.name,
    this.carModel,
    this.batteryKwh,
    this.efficiencyKmPerKwh,
    this.currentSoc,
  });

  final String? id;
  final String? phone;
  final String? name;
  final String? carModel;
  final double? batteryKwh;
  final double? efficiencyKmPerKwh;
  final double? currentSoc;

  bool get isComplete =>
      (name?.trim().isNotEmpty ?? false) &&
      (carModel?.trim().isNotEmpty ?? false) &&
      (batteryKwh ?? 0) > 0 &&
      (efficiencyKmPerKwh ?? 0) > 0;

  factory DriverProfile.fromJson(Map<String, dynamic> json) => DriverProfile(
        id: json['id']?.toString(),
        phone: json['phone']?.toString(),
        name: json['name']?.toString(),
        carModel: json['car_model']?.toString(),
        batteryKwh: double.tryParse('${json['battery_kwh']}'),
        efficiencyKmPerKwh:
            double.tryParse('${json['default_efficiency_km_per_kwh']}'),
        currentSoc: double.tryParse('${json['current_soc']}'),
      );

  DriverProfile copyWith({double? currentSoc}) => DriverProfile(
        id: id,
        phone: phone,
        name: name,
        carModel: carModel,
        batteryKwh: batteryKwh,
        efficiencyKmPerKwh: efficiencyKmPerKwh,
        currentSoc: currentSoc ?? this.currentSoc,
      );

  Map<String, dynamic> toPatch() => {
        if (name != null) 'name': name,
        if (carModel != null) 'car_model': carModel,
        if (batteryKwh != null) 'battery_kwh': batteryKwh,
        if (efficiencyKmPerKwh != null)
          'default_efficiency_km_per_kwh': efficiencyKmPerKwh,
        if (currentSoc != null) 'current_soc': currentSoc,
      };
}
