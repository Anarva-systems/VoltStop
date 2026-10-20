class Booking {
  const Booking({
    required this.id,
    required this.status,
    required this.amountInr,
    required this.slotId,
    required this.vendorId,
    this.paymentStatus,
    this.orderId,
    this.keyId,
    this.amountPaise,
    this.vendorName,
    this.vendorAddress,
    this.vendorType,
    this.serviceType,
    this.vendorLat,
    this.vendorLng,
    this.slotStartTime,
    this.slotEndTime,
  });

  final String id;
  final String status;
  final String slotId;
  final String vendorId;
  final double amountInr;
  final String? paymentStatus;
  final String? orderId;
  final String? keyId;
  final int? amountPaise;
  final String? vendorName;
  final String? vendorAddress;
  final String? vendorType;
  final String? serviceType;
  final double? vendorLat;
  final double? vendorLng;
  final DateTime? slotStartTime;
  final DateTime? slotEndTime;

  factory Booking.fromJson(Map<String, dynamic> json) => Booking(
        id: '${json['id'] ?? ''}',
        status: '${json['status'] ?? 'pending'}',
        slotId: '${json['slot_id'] ?? ''}',
        vendorId: '${json['vendor_id'] ?? ''}',
        amountInr: double.tryParse(
                '${json['amount_inr'] ?? json['amount_paid'] ?? 0}') ??
            0,
        paymentStatus:
            (json['payment_status'] ?? json['payment']?['status'])?.toString(),
        orderId: (json['razorpay_order_id'] ?? json['payment']?['order_id'])
            ?.toString(),
        keyId: (json['payment']?['key_id'])?.toString(),
        amountPaise: int.tryParse('${json['payment']?['amount_paise']}'),
        vendorName: json['vendor_name']?.toString(),
        vendorAddress: json['vendor_address']?.toString(),
        vendorType: json['vendor_type']?.toString(),
        serviceType: json['service_type']?.toString(),
        vendorLat: double.tryParse('${json['vendor_lat'] ?? ''}'),
        vendorLng: double.tryParse('${json['vendor_lng'] ?? ''}'),
        slotStartTime:
            DateTime.tryParse('${json['slot_start_time'] ?? ''}')?.toLocal(),
        slotEndTime:
            DateTime.tryParse('${json['slot_end_time'] ?? ''}')?.toLocal(),
      );
}
