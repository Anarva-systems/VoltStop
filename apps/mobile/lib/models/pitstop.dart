class Pitstop {
  const Pitstop({
    required this.id,
    required this.name,
    required this.type,
    required this.address,
    required this.distanceKm,
    required this.services,
    required this.slots,
    this.lat,
    this.lng,
    this.description,
    this.imageUrl,
    this.isVerified,
    this.isActive,
  });

  final String id;
  final String name;
  final String type;
  final String address;
  final double distanceKm;
  final double? lat;
  final double? lng;
  final String? description;
  final String? imageUrl;
  final bool? isVerified;
  final bool? isActive;
  final List<Map<String, dynamic>> services;
  final List<dynamic> slots;

  factory Pitstop.fromJson(Map<String, dynamic> source) {
    final vendor = source['vendor'] is Map
        ? Map<String, dynamic>.from(source['vendor'] as Map)
        : source;
    final servicesRaw = source['services'];
    final slotsRaw = source['availability'] ?? source['available_slots'];
    return Pitstop(
      id: '${vendor['id'] ?? source['id'] ?? ''}',
      name: '${vendor['name'] ?? 'Highway pitstop'}',
      type: '${vendor['type'] ?? 'charging'}',
      address: '${vendor['address'] ?? 'NH-16 corridor'}',
      distanceKm: double.tryParse('${source['distance_km'] ?? 0}') ?? 0,
      lat: double.tryParse('${vendor['lat']}'),
      lng: double.tryParse('${vendor['lng']}'),
      description: vendor['description']?.toString(),
      imageUrl: vendor['image_url']?.toString(),
      isVerified:
          vendor['is_verified'] is bool ? vendor['is_verified'] as bool : null,
      isActive:
          vendor['is_active'] is bool ? vendor['is_active'] as bool : null,
      services: servicesRaw is List
          ? servicesRaw
              .whereType<Map>()
              .map((value) => Map<String, dynamic>.from(value))
              .toList()
          : const [],
      slots: slotsRaw is List ? slotsRaw : const [],
    );
  }

  double? get startingPrice {
    final prices = services
        .map((service) => double.tryParse('${service['price_inr']}'))
        .whereType<double>()
        .toList();
    if (prices.isEmpty) return null;
    return prices.reduce((a, b) => a < b ? a : b);
  }

  int get availableSlotCount => slots.where((slot) {
        if (slot is! Map) return false;
        final capacity = int.tryParse('${slot['capacity'] ?? 1}') ?? 1;
        return capacity > 0;
      }).length;

  bool matchesDiscoveryCategory(String category) {
    final normalizedType = type.trim().toLowerCase().replaceAll(' ', '_');
    final serviceTypes = services
        .map((service) =>
            '${service['service_type'] ?? ''}'.trim().toLowerCase())
        .toSet();
    return switch (category) {
      'EV Charging' => const {
            'charging',
            'ev_charging',
            'charging_station',
          }.contains(normalizedType) ||
          serviceTypes
              .intersection(const {'charging', 'sleep_and_charge'}).isNotEmpty,
      'Food' => const {'restaurant', 'restaurants', 'dhaba', 'food'}
              .contains(normalizedType) ||
          serviceTypes.contains('food'),
      'Hotels' =>
        const {'hotel', 'hotels', 'lodging', 'stay'}.contains(normalizedType) ||
            serviceTypes.contains('room'),
      _ => true,
    };
  }
}
