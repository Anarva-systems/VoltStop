import 'package:flutter_test/flutter_test.dart';
import 'package:voltstop_mobile/core/services/api_client.dart';
import 'package:voltstop_mobile/repositories/driver_repository.dart';

void main() {
  test('hotel search and reservation writes use the trusted API contract', () async {
    final api = _HotelApi();
    final repository = DriverRepository(api);
    final checkIn = DateTime(2027, 4, 10);
    final checkOut = DateTime(2027, 4, 12);

    final rooms = await repository.hotelRooms(
      vendorId: 'hotel-1', checkIn: checkIn, checkOut: checkOut, guests: 2,
    );
    expect(rooms.single['room_type_id'], 'room-type-1');
    expect(api.lastGetPath, '/hotels/rooms');
    expect(api.lastQuery, {
      'vendor_id': 'hotel-1', 'check_in': '2027-04-10', 'check_out': '2027-04-12',
      'guests': 2, 'rooms': 1,
    });

    final quote = await repository.hotelQuote(
      roomTypeId: 'room-type-1', checkIn: checkIn, checkOut: checkOut, guests: 2,
    );
    expect(quote['amount_inr'], '2400.00');
    expect(api.lastPostPath, '/hotels/quotes');

    final reservation = await repository.createHotelReservation(
      roomTypeId: 'room-type-1', checkIn: checkIn, checkOut: checkOut,
      guests: 2, expectedAmountInr: '2400.00', idempotencyKey: 'retry-safe-hotel-key',
    );
    expect(reservation['status'], 'payment_pending');
    expect(api.lastPostPath, '/hotels/reservations');
    expect(api.lastHeaders, {'Idempotency-Key': 'retry-safe-hotel-key'});
    expect(api.lastBody, {
      'room_type_id': 'room-type-1', 'check_in': '2027-04-10',
      'check_out': '2027-04-12', 'guests': 2, 'rooms': 1,
      'expected_amount_inr': '2400.00',
    });
  });
}

class _HotelApi extends ApiClient {
  _HotelApi() : super(accessToken: () async => 'verified-test-token');
  String? lastGetPath;
  String? lastPostPath;
  Map<String, dynamic>? lastQuery;
  Object? lastBody;
  Map<String, String>? lastHeaders;

  @override
  Future<dynamic> get(String path, {Map<String, dynamic>? query}) async {
    lastGetPath = path;
    lastQuery = query;
    return [
      {'room_type_id': 'room-type-1', 'room_name': 'Twin room', 'nightly_rate_inr': 1200},
    ];
  }

  @override
  Future<dynamic> post(String path, {Object? data, Map<String, String>? headers}) async {
    lastPostPath = path;
    lastBody = data;
    lastHeaders = headers;
    return path == '/hotels/quotes'
        ? {'amount_inr': '2400.00', 'nights': 2}
        : {'id': 'reservation-1', 'status': 'payment_pending'};
  }
}
