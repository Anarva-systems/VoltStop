import 'package:flutter/material.dart';
import 'package:razorpay_flutter/razorpay_flutter.dart';
import '../../../controllers/app_controller.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/volt_widgets.dart';
import '../../../models/pitstop.dart';

class RestaurantMenuScreen extends StatefulWidget {
  const RestaurantMenuScreen(
      {super.key, required this.app, required this.vendor});
  final AppController app;
  final Pitstop vendor;
  @override
  State<RestaurantMenuScreen> createState() => _RestaurantMenuScreenState();
}

class _RestaurantMenuScreenState extends State<RestaurantMenuScreen> {
  final Razorpay _razorpay = Razorpay();
  late Future<Map<String, dynamic>> _menu;
  late Future<List<Map<String, dynamic>>> _orders;
  final Map<String, _CartLine> _cart = {};
  bool _showOrders = false;
  bool _busy = false;
  String? _activeOrderId;
  String? _activeRazorpayOrderId;
  String? _orderIdempotencyKey;
  String? _message;

  @override
  void initState() {
    super.initState();
    _menu = widget.app.driverRepository.restaurantMenu(widget.vendor.id);
    _orders = widget.app.driverRepository.restaurantOrders();
    _razorpay.on(Razorpay.EVENT_PAYMENT_SUCCESS, _onPaymentSuccess);
    _razorpay.on(Razorpay.EVENT_PAYMENT_ERROR, (_) => _checkOrderStatus());
    _razorpay.on(Razorpay.EVENT_EXTERNAL_WALLET, (_) => _checkOrderStatus());
  }

  @override
  void dispose() {
    _razorpay.clear();
    super.dispose();
  }

  Future<void> _add(Map<String, dynamic> item) async {
    final groups = (item['options'] as List? ?? const [])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
    final selections = <String, String>{};
    if (groups.isNotEmpty) {
      final chosen = await showDialog<Map<String, String>>(
          context: context,
          builder: (context) => StatefulBuilder(
                builder: (context, refresh) => AlertDialog(
                    title: Text('Choose ${item['name']}'),
                    content: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: groups.map((group) {
                          final name = '${group['name']}';
                          final choices =
                              (group['choices'] as List? ?? const [])
                                  .whereType<Map>()
                                  .map((e) => Map<String, dynamic>.from(e))
                                  .toList();
                          final value = selections[name] ??
                              (group['required'] == true && choices.isNotEmpty
                                  ? '${choices.first['name']}'
                                  : null);
                          if (value != null) selections[name] = value;
                          return DropdownButtonFormField<String>(
                              initialValue: value,
                              decoration: InputDecoration(labelText: name),
                              items: [
                                if (group['required'] != true)
                                  const DropdownMenuItem(
                                      value: '', child: Text('No selection')),
                                ...choices.map((choice) => DropdownMenuItem(
                                    value: '${choice['name']}',
                                    child: Text(
                                        '${choice['name']}${(num.tryParse('${choice['price_delta_inr']}') ?? 0) == 0 ? '' : ' (+₹${choice['price_delta_inr']})'}'))),
                              ],
                              onChanged: (next) => refresh(() {
                                    if (next == null || next.isEmpty) {
                                      selections.remove(name);
                                    } else {
                                      selections[name] = next;
                                    }
                                  }));
                        }).toList()),
                    actions: [
                      TextButton(
                          onPressed: () => Navigator.pop(context),
                          child: const Text('Cancel')),
                      FilledButton(
                          onPressed: () => Navigator.pop(
                              context, Map<String, String>.from(selections)),
                          child: const Text('Add'))
                    ]),
              ));
      if (chosen == null || !mounted) return;
      selections
        ..clear()
        ..addAll(chosen);
    }
    setState(() {
      final id = '${item['id']}';
      final old = _cart[id];
      _orderIdempotencyKey = null;
      _cart[id] =
          _CartLine(item, (old?.quantity ?? 0) + 1, old?.options ?? selections);
    });
  }

  Future<void> _checkout() async {
    if (_busy || _cart.isEmpty) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final idempotencyKey = _orderIdempotencyKey ??=
          'restaurant-${DateTime.now().microsecondsSinceEpoch}-${widget.vendor.id}';
      final result = await widget.app.driverRepository.createRestaurantOrder(
        vendorId: widget.vendor.id,
        items: _cart.values
            .map((line) => {
                  'item_id': line.item['id'],
                  'quantity': line.quantity,
                  'options': line.options.entries
                      .map((e) => {'group': e.key, 'choice': e.value})
                      .toList()
                })
            .toList(),
        idempotencyKey: idempotencyKey,
      );
      _activeOrderId = '${result['id']}';
      final payment =
          Map<String, dynamic>.from(result['payment'] as Map? ?? const {});
      if (payment['order_id'] == null ||
          payment['key_id'] == null ||
          payment['amount_paise'] is! num) {
        throw StateError(
            'Verified payment details are unavailable. The order remains pending on the server.');
      }
      _activeRazorpayOrderId = '${payment['order_id']}';
      if (!mounted) return;
      final confirm = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
                title: const Text('Confirm pickup order'),
                content: Text(
                    'Server-calculated total: ₹${result['total_inr']}\n\n${_cart.values.map((line) => '${line.quantity} × ${line.item['name']}').join('\n')}\n\nPayment remains pending until VoltStop verifies it.'),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(context, false),
                      child: const Text('Review later')),
                  FilledButton(
                      onPressed: () => Navigator.pop(context, true),
                      child: const Text('Continue to secure payment'))
                ],
              ));
      if (confirm != true || !mounted) {
        if (mounted)
          setState(() {
            _busy = false;
            _message =
                'Order is pending payment and will expire automatically if not paid.';
            _orders = widget.app.driverRepository.restaurantOrders();
          });
        return;
      }
      setState(() {
        _busy = false;
        _message =
            'Complete payment. The order is placed only after VoltStop verifies it.';
      });
      _razorpay.open({
        'key': payment['key_id'],
        'order_id': payment['order_id'],
        'amount': payment['amount_paise'],
        'currency': 'INR',
        'name': 'VoltStop',
        'description': 'Pickup order at ${widget.vendor.name}',
        'timeout': 300,
        'prefill': {'contact': widget.app.profile?.phone ?? ''}
      });
    } catch (error) {
      if (mounted)
        setState(() {
          _busy = false;
          _message = '$error';
        });
    }
  }

  Future<void> _openCart() async {
    if (_cart.isEmpty) return;
    final proceed = await showDialog<bool>(
        context: context,
        builder: (context) => StatefulBuilder(
            builder: (context, refresh) => AlertDialog(
                  title: const Text('Review your cart'),
                  content: SizedBox(
                      width: 480,
                      child: Column(mainAxisSize: MainAxisSize.min, children: [
                        Flexible(
                            child: ListView(
                                shrinkWrap: true,
                                children: _cart.entries.map((entry) {
                                  final line = entry.value;
                                  final optionText = line.options.entries
                                      .map((value) =>
                                          '${value.key}: ${value.value}')
                                      .join(' · ');
                                  return ListTile(
                                      title: Text('${line.item['name']}'),
                                      subtitle: Text(
                                          '${line.quantity} × ₹${line.item['price_inr']}${optionText.isEmpty ? '' : '\n$optionText'}'),
                                      trailing: Row(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            IconButton(
                                                tooltip: 'Remove one',
                                                onPressed: () =>
                                                    refresh(() => setState(() {
                                                          _orderIdempotencyKey =
                                                              null;
                                                          if (line.quantity <=
                                                              1) {
                                                            _cart.remove(
                                                                entry.key);
                                                          } else {
                                                            _cart[entry.key] =
                                                                _CartLine(
                                                                    line.item,
                                                                    line.quantity -
                                                                        1,
                                                                    line.options);
                                                          }
                                                        })),
                                                icon: const Icon(Icons
                                                    .remove_circle_outline)),
                                            Text('${line.quantity}',
                                                style: const TextStyle(
                                                    fontWeight:
                                                        FontWeight.w700)),
                                            IconButton(
                                                tooltip: 'Add one',
                                                onPressed: () =>
                                                    refresh(() => setState(() {
                                                          _orderIdempotencyKey =
                                                              null;
                                                          _cart[entry.key] =
                                                              _CartLine(
                                                                  line.item,
                                                                  line.quantity +
                                                                      1,
                                                                  line.options);
                                                        })),
                                                icon: const Icon(
                                                    Icons.add_circle_outline)),
                                          ]));
                                }).toList())),
                        const Text(
                            'The API calculates the final price; you will confirm it before payment.',
                            style: TextStyle(color: VoltColors.muted)),
                      ])),
                  actions: [
                    TextButton(
                        onPressed: () => Navigator.pop(context, false),
                        child: const Text('Keep browsing')),
                    FilledButton(
                        onPressed: _cart.isEmpty
                            ? null
                            : () => Navigator.pop(context, true),
                        child: const Text('Continue'))
                  ],
                )));
    if (proceed == true && mounted) await _checkout();
  }

  Future<void> _checkOrderStatus() async {
    final id = _activeOrderId;
    if (id == null) return;
    for (var attempt = 0; attempt < 10; attempt++) {
      try {
        final orders = await widget.app.driverRepository.restaurantOrders();
        Map<String, dynamic>? order;
        for (final item in orders) {
          if ('${item['id']}' == id) {
            order = item;
            break;
          }
        }
        if (order != null && '${order['status']}' != 'payment_pending') {
          if (mounted)
            setState(() {
              _message =
                  'Server status: ${order!['status']}. Payment: ${order['payment_status']}.';
              _orders = widget.app.driverRepository.restaurantOrders();
            });
          if (mounted && '${order['status']}' == 'placed') {
            setState(() {
              _cart.clear();
              _orderIdempotencyKey = null;
            });
          } else if (mounted &&
              const {'payment_failed', 'payment_expired', 'cancelled'}
                  .contains('${order['status']}')) {
            setState(() => _orderIdempotencyKey = null);
          }
          return;
        }
      } catch (_) {/* Provider callbacks are not authoritative. */}
      await Future<void>.delayed(const Duration(seconds: 2));
    }
    if (mounted)
      setState(() => _message =
          'Confirmation is pending. Check My orders for the server-verified status before retrying.');
  }

  Future<void> _onPaymentSuccess(PaymentSuccessResponse response) async {
    final orderId = response.orderId ?? _activeRazorpayOrderId;
    final paymentId = response.paymentId;
    final signature = response.signature;
    if (orderId != null && paymentId != null && signature != null) {
      try {
        await widget.app.driverRepository.verifyRazorpayCheckout(
          orderId: orderId,
          paymentId: paymentId,
          signature: signature,
        );
      } catch (_) {
        // The status endpoint remains authoritative if the network is transiently unavailable.
      }
    }
    await _checkOrderStatus();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: Text(widget.vendor.name), actions: [
        IconButton(
            tooltip: 'Refresh',
            onPressed: () => setState(() {
                  _menu = widget.app.driverRepository
                      .restaurantMenu(widget.vendor.id);
                  _orders = widget.app.driverRepository.restaurantOrders();
                }),
            icon: const Icon(Icons.refresh)),
      ]),
      body: Column(children: [
        Padding(
            padding: const EdgeInsets.all(12),
            child: SegmentedButton<bool>(
                segments: const [
                  ButtonSegment(
                      value: false,
                      label: Text('Menu'),
                      icon: Icon(Icons.restaurant_menu)),
                  ButtonSegment(
                      value: true,
                      label: Text('My orders'),
                      icon: Icon(Icons.receipt_long)),
                ],
                selected: {
                  _showOrders
                },
                onSelectionChanged: (value) =>
                    setState(() => _showOrders = value.first))),
        Expanded(child: _showOrders ? _orderList() : _menuList()),
        if (!_showOrders && _cart.isNotEmpty)
          SafeArea(
              top: false,
              child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                          onPressed: _busy ? null : _openCart,
                          icon: _busy
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child:
                                      CircularProgressIndicator(strokeWidth: 2))
                              : const Icon(Icons.shopping_cart_checkout),
                          label: Text(_busy
                              ? 'Creating secure order…'
                              : 'Review cart · ${_cart.values.fold<int>(0, (n, line) => n + line.quantity)} items'))))),
        if (_message != null)
          Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
              child: Text(_message!,
                  style: const TextStyle(color: VoltColors.muted))),
      ]));

  Widget _menuList() => FutureBuilder<Map<String, dynamic>>(
      future: _menu,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting)
          return const VoltLoading(label: 'Loading restaurant menu…');
        if (snapshot.hasError)
          return VoltError(
              message: '${snapshot.error}',
              onRetry: () => setState(() => _menu = widget.app.driverRepository
                  .restaurantMenu(widget.vendor.id)));
        final categories = (snapshot.data?['categories'] as List? ?? const [])
            .whereType<Map>()
            .toList();
        final hasAvailableItems = categories.any(
            (category) => (category['items'] as List? ?? const []).isNotEmpty);
        if (!hasAvailableItems)
          return const Center(
              child: Text(
                  'No menu items are currently available. Please check again later.'));
        return ListView(
            padding: const EdgeInsets.all(16),
            children: categories
                .expand((category) => [
                      Padding(
                          padding: const EdgeInsets.symmetric(vertical: 10),
                          child: Text('${category['name']}',
                              style: Theme.of(context)
                                  .textTheme
                                  .titleLarge
                                  ?.copyWith(fontWeight: FontWeight.w800))),
                      ...(category['items'] as List? ?? const [])
                          .whereType<Map>()
                          .map((raw) {
                        final item = Map<String, dynamic>.from(raw);
                        final qty = _cart['${item['id']}']?.quantity ?? 0;
                        return Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: VoltCard(
                                child: Row(children: [
                              Expanded(
                                  child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                    Text('${item['name']}',
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w800)),
                                    if ('${item['description'] ?? ''}'
                                        .isNotEmpty)
                                      Text('${item['description']}',
                                          style: const TextStyle(
                                              color: VoltColors.muted)),
                                    Text('₹${item['price_inr']}',
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w700)),
                                  ])),
                              IconButton(
                                  tooltip: 'Add ${item['name']} to order',
                                  onPressed: item['is_available'] == true
                                      ? () => _add(item)
                                      : null,
                                  icon: Icon(qty > 0
                                      ? Icons.add_circle
                                      : Icons.add_circle_outline)),
                              if (qty > 0) Text('$qty')
                            ])));
                      }),
                    ])
                .toList());
      });

  Widget _orderList() => FutureBuilder<List<Map<String, dynamic>>>(
      future: _orders,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting)
          return const VoltLoading(label: 'Loading your orders…');
        if (snapshot.hasError)
          return VoltError(
              message: '${snapshot.error}',
              onRetry: () => setState(() =>
                  _orders = widget.app.driverRepository.restaurantOrders()));
        final orders = snapshot.data ?? const [];
        if (orders.isEmpty)
          return const Center(
              child: Text(
                  'Your restaurant orders will appear here after checkout.'));
        return ListView(
            padding: const EdgeInsets.all(16),
            children: orders.map((order) {
              final items = order['items'] as List? ?? const [];
              return Card(
                  child: ExpansionTile(
                      title: Text(
                          '${order['restaurant_name']} · ₹${order['total_inr']}'),
                      subtitle: Text(
                          '${order['status']} · payment ${order['payment_status'] ?? 'pending'}${order['webhook_verified'] == true ? ' (verified)' : ''}'),
                      children: items
                          .whereType<Map>()
                          .map((item) => ListTile(
                              title:
                                  Text('${item['name']} × ${item['quantity']}'),
                              subtitle:
                                  Text('${item['selected_options'] ?? ''}'),
                              trailing: Text('₹${item['line_total_inr']}')))
                          .toList()));
            }).toList());
      });
}

class _CartLine {
  const _CartLine(this.item, this.quantity, this.options);
  final Map<String, dynamic> item;
  final int quantity;
  final Map<String, String> options;
}
