class DriverTrip {
  const DriverTrip({
    required this.id,
    required this.origin,
    required this.destination,
    required this.departureAt,
    required this.vehicleMake,
    required this.vehicleModel,
    required this.availableSeats,
    required this.status,
    this.estimatedArrivalAt,
    this.vehicleId,
    this.notes,
    this.isDiscoverable = false,
    this.startedAt,
    this.completedAt,
    this.cancelledAt,
    this.routePlan,
    this.recommendedPitstops = const [],
  });

  final String id;
  final String origin;
  final String destination;
  final DateTime departureAt;
  final DateTime? estimatedArrivalAt;
  final String? vehicleId;
  final String vehicleMake;
  final String vehicleModel;
  final int availableSeats;
  final String? notes;
  final bool isDiscoverable;
  final String status;
  final DateTime? startedAt;
  final DateTime? completedAt;
  final DateTime? cancelledAt;
  final Map<String, dynamic>? routePlan;
  final List<Map<String, dynamic>> recommendedPitstops;

  String get vehicleName => '$vehicleMake $vehicleModel'.trim();

  factory DriverTrip.fromJson(Map<String, dynamic> json) => DriverTrip(
        id: '${json['id']}',
        origin: '${json['origin'] ?? ''}',
        destination: '${json['destination'] ?? ''}',
        departureAt: DateTime.parse('${json['departure_at']}').toLocal(),
        estimatedArrivalAt: json['estimated_arrival_at'] == null
            ? null
            : DateTime.parse('${json['estimated_arrival_at']}').toLocal(),
        vehicleId: json['vehicle_id']?.toString(),
        vehicleMake: '${json['vehicle_make'] ?? ''}',
        vehicleModel: '${json['vehicle_model'] ?? ''}',
        availableSeats: int.tryParse('${json['available_seats']}') ?? 0,
        notes: json['notes']?.toString(),
        isDiscoverable: json['is_discoverable'] == true,
        status: '${json['status'] ?? 'scheduled'}',
        startedAt: _localDate(json['started_at']),
        completedAt: _localDate(json['completed_at']),
        cancelledAt: _localDate(json['cancelled_at']),
        routePlan: json['route_plan'] is Map
            ? Map<String, dynamic>.from(json['route_plan'] as Map)
            : null,
        recommendedPitstops: (json['recommended_pitstops'] as List? ?? const [])
            .whereType<Map>()
            .map((item) => Map<String, dynamic>.from(item))
            .toList(growable: false),
      );

  static DateTime? _localDate(dynamic value) =>
      value == null ? null : DateTime.parse('$value').toLocal();
}
