import 'dart:async';
import 'dart:ui' as ui;
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:razorpay_flutter/razorpay_flutter.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../../controllers/app_controller.dart';
import '../../auth/views/auth_screens.dart';
import '../../../core/config/app_config.dart';
import '../../../core/services/api_client.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/volt_widgets.dart';
import '../../../models/booking.dart';
import '../../../models/driver_profile.dart';
import '../../../models/pitstop.dart';
import 'dispute_screens.dart';
import 'vehicles_screen.dart';
import 'restaurant_screens.dart';
import 'upcoming_trips_screen.dart';

class ProfileSetupScreen extends StatefulWidget {
  const ProfileSetupScreen({super.key, required this.app});
  final AppController app;
  @override
  State<ProfileSetupScreen> createState() => _ProfileSetupScreenState();
}

class _ProfileSetupScreenState extends State<ProfileSetupScreen> {
  final _name = TextEditingController();
  final _make = TextEditingController();
  final _model = TextEditingController();
  final _battery = TextEditingController();
  final _efficiency = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final profile = widget.app.profile;
    _name.text = profile?.name ?? '';
    _make.text = widget.app.activeVehicle?.make ?? '';
    _model.text = widget.app.activeVehicle?.model ?? profile?.carModel ?? '';
    _battery.text = profile?.batteryKwh?.toString() ?? '';
    _efficiency.text = profile?.efficiencyKmPerKwh?.toString() ?? '';
  }

  @override
  void dispose() {
    _name.dispose();
    _make.dispose();
    _model.dispose();
    _battery.dispose();
    _efficiency.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final battery = double.tryParse(_battery.text);
    final efficiency = double.tryParse(_efficiency.text);
    if (_name.text.trim().isEmpty ||
        _make.text.trim().isEmpty ||
        _model.text.trim().isEmpty ||
        battery == null ||
        efficiency == null ||
        battery <= 0 ||
        efficiency <= 0) {
      setState(() => _error =
          'Enter a name, vehicle make and model, battery capacity and efficiency greater than zero.');
      return;
    }
    if (battery > 500) {
      setState(() => _error = 'Battery capacity must be 500 kWh or less.');
      return;
    }
    if (efficiency > 20) {
      setState(() => _error =
          'Efficiency must be 20 km/kWh or less. Enter efficiency per kWh, not total driving range.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.app.saveProfile(DriverProfile(
        id: widget.app.profile?.id,
        phone: widget.app.profile?.phone,
        name: _name.text.trim(),
        carModel: '${_make.text.trim()} ${_model.text.trim()}',
        batteryKwh: battery,
        efficiencyKmPerKwh: efficiency,
        currentSoc: widget.app.profile?.currentSoc,
      ));
      if (widget.app.vehicles.isEmpty) {
        await widget.app.driverRepository.createVehicle(
          make: _make.text.trim(),
          model: _model.text.trim(),
          vehicleType: 'car',
          batteryKwh: battery,
          efficiencyKmPerKwh: efficiency,
          currentSoc: widget.app.profile?.currentSoc,
          isDefault: true,
        );
        await widget.app.refreshVehicles();
      } else if (widget.app.activeVehicle != null) {
        final vehicle = widget.app.activeVehicle!;
        await widget.app.driverRepository.updateVehicle(vehicle.id, {
          'make': _make.text.trim(),
          'model': _model.text.trim(),
          'battery_kwh': battery,
          'efficiency_km_per_kwh': efficiency,
        });
        await widget.app.refreshVehicles();
      }
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => DriverShell(app: widget.app)),
          (_) => false);
    } catch (error) {
      if (mounted) setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
          body: SafeArea(
              child: ListView(padding: const EdgeInsets.all(22), children: [
        const BrandMark(),
        const SizedBox(height: 25),
        const LinearProgressIndicator(
            value: .66,
            color: VoltColors.green,
            backgroundColor: VoltColors.border),
        const SizedBox(height: 28),
        const Icon(Icons.electric_car, color: VoltColors.green, size: 48),
        const SizedBox(height: 10),
        Text('Set up your VoltPass',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 8),
        const Text(
            'Add your driver and vehicle details to personalize energy estimates.',
            textAlign: TextAlign.center,
            style: TextStyle(color: VoltColors.muted)),
        const SizedBox(height: 28),
        _input(_name, 'Driver full name', Icons.person_outline),
        const SizedBox(height: 12),
        _input(_make, 'Vehicle make', Icons.directions_car_outlined),
        const SizedBox(height: 12),
        _input(_model, 'EV model', Icons.electric_car_outlined),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
              child: _input(
                  _battery, 'Battery (kWh)', Icons.battery_charging_full,
                  keyboard:
                      const TextInputType.numberWithOptions(decimal: true))),
          const SizedBox(width: 12),
          Expanded(
              child: _input(_efficiency, 'Efficiency', Icons.speed,
                  keyboard:
                      const TextInputType.numberWithOptions(decimal: true)))
        ]),
        const SizedBox(height: 8),
        const Text(
            'Efficiency means kilometres per kWh, not total driving range. Enter a value from 0 to 20; check your owner’s manual if unsure.',
            style: TextStyle(color: VoltColors.muted, fontSize: 12)),
        if (_error != null)
          Padding(
              padding: const EdgeInsets.only(top: 12),
              child:
                  Text(_error!, style: const TextStyle(color: VoltColors.red))),
        const SizedBox(height: 20),
        SizedBox(
            width: double.infinity,
            child: FilledButton(
                onPressed: _busy ? null : _save,
                child: _busy
                    ? const CircularProgressIndicator()
                    : const Text('Complete setup'))),
      ])));

  Widget _input(TextEditingController controller, String label, IconData icon,
          {TextInputType? keyboard}) =>
      TextField(
          controller: controller,
          keyboardType: keyboard,
          decoration:
              InputDecoration(labelText: label, prefixIcon: Icon(icon)));
}

class DriverShell extends StatefulWidget {
  const DriverShell({super.key, required this.app, this.initialIndex = 0});
  final AppController app;
  final int initialIndex;
  @override
  State<DriverShell> createState() => _DriverShellState();
}

class _DriverShellState extends State<DriverShell> {
  late int _index;

  @override
  void initState() {
    super.initState();
    _index = widget.initialIndex;
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      HomeScreen(app: widget.app, onExplore: () => setState(() => _index = 1)),
      DiscoveryScreen(app: widget.app, isActive: _index == 1),
      DriverTripsScreen(
        app: widget.app,
        reservations: BookingsScreen(app: widget.app),
      ),
      ProfileScreen(app: widget.app)
    ];
    return Scaffold(
      body: SafeArea(child: IndexedStack(index: _index, children: pages)),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) => setState(() => _index = value),
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.home_outlined),
              selectedIcon: Icon(Icons.home),
              label: 'Home'),
          NavigationDestination(
              icon: Icon(Icons.explore_outlined),
              selectedIcon: Icon(Icons.explore),
              label: 'Explore'),
          NavigationDestination(
              icon: Icon(Icons.route_outlined),
              selectedIcon: Icon(Icons.route),
              label: 'Trips'),
          NavigationDestination(
              icon: Icon(Icons.person_outline),
              selectedIcon: Icon(Icons.person),
              label: 'Profile'),
        ],
      ),
    );
  }
}

class _JourneyWelcomeCard extends StatelessWidget {
  const _JourneyWelcomeCard({
    required this.origin,
    required this.destination,
    required this.stateOfCharge,
    this.driverName,
  });

  final String origin;
  final String destination;
  final double? stateOfCharge;
  final String? driverName;

  @override
  Widget build(BuildContext context) {
    final firstName = driverName?.trim().split(RegExp(r'\s+')).first;
    final greeting = firstName == null || firstName.isEmpty
        ? 'Where to next?'
        : 'Where to next, $firstName?';

    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(VoltRadii.card + 4),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF214F40), Color(0xFF173B32)],
        ),
        boxShadow: const [
          BoxShadow(
            color: Color(0x1F183E32),
            blurRadius: 22,
            offset: Offset(0, 10),
          ),
        ],
      ),
      child: Stack(
        children: [
          Positioned(
            top: 0,
            right: 0,
            child: IgnorePointer(
              child: CustomPaint(
                size: const Size(120, 66),
                painter: _JourneyRoutePainter(),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(19, 18, 19, 17),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Icon(Icons.bolt_rounded,
                        color: VoltColors.lime, size: 16),
                    const SizedBox(width: 6),
                    const Text(
                      'YOUR NEXT DRIVE',
                      style: TextStyle(
                        color: Color(0xFFE0ECD7),
                        fontSize: 9,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 1.1,
                      ),
                    ),
                    const Spacer(),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 9, vertical: 5),
                      decoration: BoxDecoration(
                        color: const Color(0x1FFFFFFF),
                        borderRadius: BorderRadius.circular(VoltRadii.pill),
                        border: Border.all(color: const Color(0x26FFFFFF)),
                      ),
                      child: const Text(
                        'NH–16',
                        style: TextStyle(
                          color: Color(0xFFF0F5E6),
                          fontSize: 8,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 0.8,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 13),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            greeting,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: VoltColors.surface,
                              fontFamily: 'serif',
                              fontSize: 25,
                              fontWeight: FontWeight.w600,
                              height: 1.02,
                              letterSpacing: -0.5,
                            ),
                          ),
                          const SizedBox(height: 7),
                          const Text(
                            'A smoother drive starts with a better stop.',
                            style: TextStyle(
                              color: Color(0xFFD5E1D7),
                              fontSize: 11,
                              height: 1.4,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 12),
                    _ChargeRing(stateOfCharge: stateOfCharge),
                  ],
                ),
                const SizedBox(height: 13),
                Container(
                  width: double.infinity,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 11, vertical: 10),
                  decoration: BoxDecoration(
                    color: const Color(0x18FFFFFF),
                    borderRadius: BorderRadius.circular(13),
                    border: Border.all(color: const Color(0x24FFFFFF)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.trip_origin_rounded,
                          color: VoltColors.lime, size: 15),
                      const SizedBox(width: 7),
                      Expanded(
                        child: Text(
                          origin,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: VoltColors.surface,
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                      const Padding(
                        padding: EdgeInsets.symmetric(horizontal: 7),
                        child: Icon(Icons.arrow_forward_rounded,
                            color: Color(0xFFB9D6B6), size: 15),
                      ),
                      const Icon(Icons.location_on_rounded,
                          color: Color(0xFF9CE0AD), size: 15),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          destination,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          textAlign: TextAlign.right,
                          style: const TextStyle(
                            color: VoltColors.surface,
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ChargeRing extends StatelessWidget {
  const _ChargeRing({required this.stateOfCharge});

  final double? stateOfCharge;

  @override
  Widget build(BuildContext context) => SizedBox(
        width: 62,
        height: 62,
        child: Stack(
          alignment: Alignment.center,
          children: [
            TweenAnimationBuilder<double>(
              tween: Tween<double>(
                begin: 0,
                end: ((stateOfCharge ?? 0).clamp(0, 100)) / 100,
              ),
              duration: const Duration(milliseconds: 650),
              curve: Curves.easeOutCubic,
              builder: (context, value, _) => CircularProgressIndicator(
                value: stateOfCharge == null ? 0 : value,
                strokeWidth: 5,
                strokeCap: StrokeCap.round,
                backgroundColor: const Color(0x35FFFFFF),
                valueColor:
                    const AlwaysStoppedAnimation<Color>(VoltColors.lime),
              ),
            ),
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 220),
              child: Column(
                key: ValueKey(stateOfCharge?.round()),
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    stateOfCharge == null ? '—' : '${stateOfCharge!.round()}%',
                    style: const TextStyle(
                      color: VoltColors.surface,
                      fontSize: 13,
                      fontWeight: FontWeight.w800,
                      height: 1,
                    ),
                  ),
                  const SizedBox(height: 3),
                  const Text(
                    'CHARGE',
                    style: TextStyle(
                      color: Color(0xFFD5E1D7),
                      fontSize: 7,
                      fontWeight: FontWeight.w800,
                      letterSpacing: .5,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      );
}

class _JourneyRoutePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final line = Paint()
      ..color = const Color(0x48C8E982)
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;
    final route = ui.Path()
      ..moveTo(size.width * .08, size.height * .81)
      ..cubicTo(size.width * .31, size.height * .53, size.width * .37,
          size.height * .94, size.width * .56, size.height * .64)
      ..cubicTo(size.width * .72, size.height * .39, size.width * .77,
          size.height * .56, size.width * .98, size.height * .18);
    canvas.drawPath(route, line);

    final halo = Paint()..color = const Color(0x24D8F4A4);
    final point = Paint()..color = const Color(0xB5D8F4A4);
    for (final pointAt in <Offset>[
      Offset(size.width * .08, size.height * .81),
      Offset(size.width * .56, size.height * .64),
      Offset(size.width * .98, size.height * .18),
    ]) {
      canvas.drawCircle(pointAt, 7, halo);
      canvas.drawCircle(pointAt, 3, point);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.app, required this.onExplore});
  final AppController app;
  final VoidCallback onExplore;
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  String _origin = 'Srikakulam';
  String _destination = 'Vijayawada';
  late DateTime _departureAt;
  double? _soc;
  bool _savingSoc = false;
  String? _socSaveError;
  Timer? _routeDebounce;
  Timer? _liveRefreshDebounce;
  StreamSubscription<void>? _catalogChanges;
  StreamSubscription<void>? _bookingChanges;
  late Future<Map<String, dynamic>> _route;
  late Future<List<Booking>> _bookings;

  DriverProfile get _profile => widget.app.profile ?? const DriverProfile();

  @override
  void initState() {
    super.initState();
    _departureAt = DateTime.now().add(const Duration(minutes: 10));
    _soc =
        widget.app.activeVehicle?.currentSoc ?? widget.app.profile?.currentSoc;
    _load();
    final repository = widget.app.driverRepository;
    _catalogChanges = repository.watchPitstopDirectoryChanges().listen(
          (_) => _scheduleLiveRefresh(),
          onError: (_) {},
        );
    _bookingChanges = repository.watchBookings().listen(
          (_) => _scheduleLiveRefresh(),
          onError: (_) {},
        );
  }

  void _scheduleLiveRefresh() {
    _liveRefreshDebounce?.cancel();
    _liveRefreshDebounce = Timer(const Duration(milliseconds: 180), () {
      if (!mounted) return;
      final repository = widget.app.driverRepository;
      setState(() {
        _route = _previewRoute();
        _bookings = repository.bookings();
      });
    });
  }

  Future<Map<String, dynamic>> _previewRoute() {
    final battery = widget.app.activeVehicle?.batteryKwh ?? _profile.batteryKwh;
    final efficiency = widget.app.activeVehicle?.efficiencyKmPerKwh ??
        _profile.efficiencyKmPerKwh;
    final stateOfCharge = _soc;
    if (battery == null || efficiency == null || stateOfCharge == null) {
      return Future.value(<String, dynamic>{});
    }
    return widget.app.driverRepository.planRoute(
      origin: _origin,
      destination: _destination,
      batteryKwh: battery,
      stateOfCharge: stateOfCharge,
      efficiency: efficiency,
      persist: false,
      departureAt: _departureAt,
    );
  }

  Future<void> _saveCurrentCharge(double value) async {
    setState(() {
      _savingSoc = true;
      _socSaveError = null;
    });
    try {
      final vehicle = widget.app.activeVehicle;
      if (vehicle != null) {
        await widget.app.driverRepository
            .updateVehicle(vehicle.id, {'current_soc': value});
        await widget.app.refreshVehicles();
      } else {
        final profile = widget.app.profile ?? const DriverProfile();
        await widget.app.saveProfile(profile.copyWith(currentSoc: value));
      }
    } catch (_) {
      if (mounted) {
        setState(() => _socSaveError =
            'Charge could not be saved. Check your connection and try again.');
      }
    } finally {
      if (mounted) setState(() => _savingSoc = false);
    }
  }

  void _load() {
    _route = _previewRoute();
    _bookings = widget.app.driverRepository.bookings();
  }

  @override
  void dispose() {
    _routeDebounce?.cancel();
    _liveRefreshDebounce?.cancel();
    _catalogChanges?.cancel();
    _bookingChanges?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
        onRefresh: () async => setState(_load),
        child: CustomScrollView(slivers: [
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(20, 14, 20, 26),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                Row(children: [
                  const BrandMark(compact: true),
                  const Spacer(),
                  IconButton(
                    tooltip: 'Refresh route and pitstops',
                    onPressed: () => setState(_load),
                    icon: const Icon(Icons.refresh_rounded),
                  ),
                ]),
                const SizedBox(height: 14),
                _JourneyWelcomeCard(
                  origin: _origin,
                  destination: _destination,
                  driverName: _profile.name,
                  stateOfCharge: _soc,
                ),
                const SizedBox(height: 18),
                VoltCard(
                  padding: const EdgeInsets.fromLTRB(17, 16, 17, 17),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(children: [
                        Expanded(
                          child: Text('PLAN A CHARGE-READY ROUTE',
                              style: Theme.of(context)
                                  .textTheme
                                  .labelLarge
                                  ?.copyWith(
                                      fontSize: 10,
                                      letterSpacing: 1.0,
                                      color: VoltColors.muted)),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 9, vertical: 5),
                          decoration: BoxDecoration(
                            color: VoltColors.elevated,
                            borderRadius: BorderRadius.circular(VoltRadii.pill),
                          ),
                          child: const Text('NH–16',
                              style: TextStyle(
                                  color: VoltColors.forest,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 11)),
                        ),
                      ]),
                      const SizedBox(height: 5),
                      Text(
                        'Pick any town along the NH–16 pilot route.',
                        style: Theme.of(context)
                            .textTheme
                            .bodySmall
                            ?.copyWith(color: VoltColors.muted),
                      ),
                      const SizedBox(height: 13),
                      Row(children: [
                        Expanded(
                          child: Column(children: [
                            _routeField(
                              Icons.radio_button_checked,
                              'FROM',
                              _origin,
                              _destination,
                              (value) => setState(() {
                                _origin = value;
                                _load();
                              }),
                            ),
                            Padding(
                              padding: const EdgeInsets.only(
                                  left: 15, top: 1, bottom: 1),
                              child: Align(
                                alignment: Alignment.centerLeft,
                                child: Container(
                                    height: 16,
                                    width: 1.5,
                                    color: VoltColors.border),
                              ),
                            ),
                            _routeField(
                              Icons.location_on_outlined,
                              'TO',
                              _destination,
                              _origin,
                              (value) => setState(() {
                                _destination = value;
                                _load();
                              }),
                            ),
                          ]),
                        ),
                        const SizedBox(width: 6),
                        IconButton.filledTonal(
                          tooltip: 'Reverse route',
                          onPressed: () => setState(() {
                            final previousOrigin = _origin;
                            _origin = _destination;
                            _destination = previousOrigin;
                            _load();
                          }),
                          icon: const Icon(Icons.swap_vert_rounded),
                        ),
                      ]),
                      const SizedBox(height: 12),
                      _DeparturePicker(
                        value: _departureAt,
                        onChanged: (value) => setState(() {
                          _departureAt = value;
                          _load();
                        }),
                      ),
                      const Divider(height: 24),
                      Row(children: [
                        Expanded(
                          child: Text('Current battery charge',
                              style: Theme.of(context).textTheme.titleSmall),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          _soc == null ? 'Not set' : '${_soc!.round()}%',
                          style: Theme.of(context)
                              .textTheme
                              .titleSmall
                              ?.copyWith(color: VoltColors.forest),
                        ),
                      ]),
                      Slider(
                        value: _soc ?? 50,
                        min: 0,
                        max: 100,
                        divisions: 20,
                        label: _soc == null ? null : '${_soc!.round()}%',
                        onChanged: (value) {
                          setState(() {
                            _soc = value;
                            _route = Future.value(<String, dynamic>{});
                          });
                          _routeDebounce?.cancel();
                          _routeDebounce = Timer(
                            const Duration(milliseconds: 350),
                            () {
                              if (mounted) {
                                setState(() {
                                  _route = _previewRoute();
                                });
                              }
                            },
                          );
                        },
                        onChangeEnd: _saveCurrentCharge,
                      ),
                      if (_soc == null)
                        Text(
                            'Set your charge to estimate energy and arrival range.',
                            style: Theme.of(context).textTheme.bodySmall),
                      if (_savingSoc)
                        const Padding(
                          padding: EdgeInsets.only(top: 5),
                          child: Text('Saving current charge to your profile…'),
                        ),
                      if (_socSaveError != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 5),
                          child: Text(
                            _socSaveError!,
                            style: const TextStyle(color: VoltColors.warning),
                          ),
                        ),
                      if (_soc != null) ...[
                        const SizedBox(height: 5),
                        FutureBuilder<Map<String, dynamic>>(
                          future: _route,
                          builder: (context, snapshot) {
                            if (snapshot.connectionState ==
                                ConnectionState.waiting) {
                              return const LinearProgressIndicator();
                            }
                            if (snapshot.hasError) {
                              return Text(
                                  'Route estimate unavailable. Retry to refresh.',
                                  style: Theme.of(context).textTheme.bodySmall);
                            }
                            final data = snapshot.data ?? const {};
                            final distance =
                                double.tryParse('${data['distance_km']}');
                            final energy = double.tryParse(
                                '${data['estimated_consumption_kwh']}');
                            final arrival = double.tryParse(
                                '${data['estimated_remaining_soc']}');
                            if (distance == null ||
                                energy == null ||
                                arrival == null) {
                              return Text('Route estimate is being prepared.',
                                  style: Theme.of(context).textTheme.bodySmall);
                            }
                            return Row(children: [
                              Expanded(
                                  child: _metric(
                                      'DISTANCE', '${distance.round()} km')),
                              Expanded(
                                  child: _metric(
                                      'ENERGY*', '${energy.round()} kWh')),
                              Expanded(
                                  child: _metric('ARRIVAL SoC',
                                      '${arrival.clamp(0, 100).round()}%')),
                            ]);
                          },
                        ),
                      ],
                      const SizedBox(height: 13),
                      SizedBox(
                        width: double.infinity,
                        child: OutlinedButton.icon(
                          onPressed: () => Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) => RoutePlannerScreen(
                                app: widget.app,
                                origin: _origin,
                                destination: _destination,
                                soc: _soc,
                                departureAt: _departureAt,
                              ),
                            ),
                          ),
                          icon: const Icon(Icons.map_outlined),
                          label: const Text('View route & stops'),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text('*Route energy and arrival charge are estimates.',
                          style: Theme.of(context).textTheme.bodySmall),
                    ],
                  ),
                ),
                const SizedBox(height: 19),
                Row(children: [
                  Expanded(
                    child: Text('Stops on your route',
                        style: Theme.of(context).textTheme.titleLarge),
                  ),
                  TextButton(
                    onPressed: widget.onExplore,
                    child: const Text('Explore all'),
                  ),
                ]),
                Text('Charging, food and stays · $_origin to $_destination',
                    style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 11),
                FutureBuilder<Map<String, dynamic>>(
                  future: _route,
                  builder: (context, snapshot) {
                    if (snapshot.connectionState == ConnectionState.waiting) {
                      return const VoltLoading(
                          label: 'Finding stops along your route…');
                    }
                    if (snapshot.hasError) {
                      return VoltError(
                        message: 'Stops for this route could not be loaded.',
                        onRetry: () {
                          setState(() => _route = _previewRoute());
                        },
                      );
                    }
                    final data = snapshot.data ?? const <String, dynamic>{};
                    final stops = _routePitstops(data);
                    if (stops.isEmpty) {
                      final hasVehicle = widget.app.profileComplete;
                      return VoltCard(
                        child: Text(
                          hasVehicle
                              ? 'No partner stops are listed near this route yet. Try Explore to search around a town or your current location.'
                              : 'Add your EV details and current battery charge to see route stops and energy estimates.',
                          style: const TextStyle(color: VoltColors.muted),
                        ),
                      );
                    }
                    return Column(
                      children: stops
                          .take(2)
                          .map((vendor) => Padding(
                                padding: const EdgeInsets.only(bottom: 11),
                                child: PitstopCard(
                                  vendor: vendor,
                                  onTap: () => _openVendor(context, vendor),
                                ),
                              ))
                          .toList(),
                    );
                  },
                ),
                const SizedBox(height: 8),
                Text('Next reservation',
                    style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 9),
                _upcomingBooking(context),
              ]),
            ),
          ),
        ]),
      );

  Widget _routeField(
    IconData icon,
    String label,
    String value,
    String unavailableStop,
    ValueChanged<String> onChanged,
  ) =>
      Row(
        children: [
          Icon(icon,
              size: 17,
              color: label == 'TO' ? VoltColors.forest : VoltColors.muted),
          const SizedBox(width: 10),
          Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(label,
                  style: const TextStyle(
                      color: VoltColors.muted,
                      fontSize: 9,
                      letterSpacing: 0.8,
                      fontWeight: FontWeight.w800)),
              const SizedBox(height: 2),
              DropdownButton<String>(
                value: value,
                isDense: true,
                underline: const SizedBox.shrink(),
                items: nh16PilotStops
                    .where((stop) => stop == value || stop != unavailableStop)
                    .map((stop) => DropdownMenuItem(
                          value: stop,
                          child: Text(stop),
                        ))
                    .toList(growable: false),
                onChanged: (next) {
                  if (next != null) onChanged(next);
                },
              ),
            ]),
          ),
        ],
      );
  Widget _metric(String label, String value) => Column(children: [
        Text(label,
            textAlign: TextAlign.center,
            style: const TextStyle(
                color: VoltColors.muted,
                fontSize: 9,
                fontWeight: FontWeight.w800)),
        const SizedBox(height: 4),
        Text(value,
            textAlign: TextAlign.center,
            style: const TextStyle(
                fontWeight: FontWeight.w900, color: VoltColors.cyan))
      ]);
  Widget _upcomingBooking(BuildContext context) => FutureBuilder<List<Booking>>(
      future: _bookings,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting)
          return const Padding(
              padding: EdgeInsets.all(16), child: LinearProgressIndicator());
        if (snapshot.hasError)
          return VoltError(
              message: 'Upcoming bookings could not be loaded.',
              onRetry: () => setState(
                  () => _bookings = widget.app.driverRepository.bookings()));
        final list = snapshot.data!
            .where((b) => b.status == 'confirmed' || b.status == 'pending')
            .toList();
        if (list.isEmpty)
          return const VoltCard(
              child: Text(
                  'No upcoming reservations. Choose a pitstop to reserve a charging slot.',
                  style: TextStyle(color: VoltColors.muted)));
        final booking = list.first;
        return ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const CircleAvatar(
                backgroundColor: VoltColors.elevated,
                child: Icon(Icons.ev_station, color: VoltColors.green)),
            title: Text(
                'Reservation ${booking.id.substring(0, booking.id.length.clamp(0, 8).toInt())}'),
            subtitle: Text('Status: ${booking.status}'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                    builder: (_) => BookingDetailsScreen(
                        app: widget.app, booking: booking))));
      });
  void _openVendor(BuildContext context, Pitstop vendor) => Navigator.push(
      context,
      MaterialPageRoute(
          builder: (_) =>
              PitstopDetailsScreen(app: widget.app, vendorId: vendor.id)));
}

class _RoutePreview extends StatelessWidget {
  const _RoutePreview(
      {this.data, this.origin = 'Srikakulam', this.destination = 'Vijayawada'});
  final Map<String, dynamic>? data;
  final String origin;
  final String destination;
  @override
  Widget build(BuildContext context) {
    final coords = data?['route_coordinates'];
    final points = coords is List
        ? coords
            .whereType<List>()
            .where((p) => p.length >= 2)
            .map((p) =>
                LatLng((p[1] as num).toDouble(), (p[0] as num).toDouble()))
            .toList()
        : <LatLng>[];
    if (points.length >= 2) {
      final stops = data?['recommended_pitstops'];
      final markers = <Marker>[
        Marker(
            point: points.first,
            width: 36,
            height: 36,
            child: const Icon(Icons.location_on,
                color: VoltColors.cyan, size: 28)),
        Marker(
            point: points.last,
            width: 36,
            height: 36,
            child: const Icon(Icons.flag, color: VoltColors.cyan, size: 28)),
      ];
      if (stops is List) {
        for (final stop in stops.whereType<Map>()) {
          final vendor = stop['vendor'];
          if (vendor is! Map) continue;
          final lat = double.tryParse('${vendor['lat']}');
          final lng = double.tryParse('${vendor['lng']}');
          final id = vendor['id']?.toString();
          if (lat == null || lng == null || id == null) continue;
          final pitstop = Pitstop.fromJson(Map<String, dynamic>.from(stop));
          markers.add(Marker(
              point: LatLng(lat, lng),
              width: 36,
              height: 36,
              child: Tooltip(
                  message:
                      '${vendor['name'] ?? 'Route stop'} · ${_serviceName(pitstop.type)}',
                  child: Icon(_pitstopIcon(pitstop),
                      color: _pitstopColor(pitstop), size: 26))));
        }
      }
      Widget legend(IconData icon, String label, Color color) => Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 14, color: color),
              const SizedBox(width: 4),
              Text(label,
                  style:
                      const TextStyle(color: VoltColors.muted, fontSize: 10)),
            ],
          );
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(18),
            child: SizedBox(
              height: 205,
              child: FlutterMap(
                options: MapOptions(
                    initialCenter: points[points.length ~/ 2],
                    initialZoom: 7.3),
                children: [
                  TileLayer(
                      urlTemplate: AppConfig.osmTileUrl,
                      userAgentPackageName: 'com.voltstop.app'),
                  PolylineLayer(polylines: [
                    Polyline(
                        points: points, color: VoltColors.cyan, strokeWidth: 5)
                  ]),
                  MarkerLayer(markers: markers),
                  RichAttributionWidget(attributions: [
                    TextSourceAttribution('OpenStreetMap contributors',
                        onTap: () => launchUrl(
                            Uri.parse('https://openstreetmap.org/copyright'))),
                  ]),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 13,
            runSpacing: 6,
            children: [
              legend(Icons.ev_station_rounded, 'Charging', VoltColors.forest),
              legend(Icons.restaurant_rounded, 'Food', VoltColors.green),
              legend(Icons.hotel_rounded, 'Stay', VoltColors.cyan),
            ],
          ),
        ],
      );
    }
    return VoltCard(
        padding: const EdgeInsets.all(12),
        child: SizedBox(
            height: 155,
            child: Stack(alignment: Alignment.center, children: [
              Positioned.fill(child: CustomPaint(painter: _RoutePainter())),
              Positioned(
                  left: 6, top: 0, child: _MapTag(text: 'Origin • $origin')),
              Positioned(
                  right: 3,
                  bottom: 0,
                  child: _MapTag(text: 'Destination • $destination')),
              const Center(
                  child:
                      _MapTag(text: 'NH-16 corridor schematic', green: true)),
            ])));
  }
}

class _MapTag extends StatelessWidget {
  const _MapTag({required this.text, this.green = false});
  final String text;
  final bool green;
  @override
  Widget build(BuildContext context) => Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
      decoration: BoxDecoration(
          color: green ? VoltColors.lime : VoltColors.elevated,
          borderRadius: BorderRadius.circular(9)),
      child: Text(text,
          style: const TextStyle(
              color: VoltColors.forest,
              fontWeight: FontWeight.w700,
              fontSize: 10)));
}

class _RoutePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final path = ui.Path()
      ..moveTo(size.width * .05, size.height * .75)
      ..cubicTo(size.width * .35, size.height * .72, size.width * .35,
          size.height * .25, size.width * .68, size.height * .45)
      ..quadraticBezierTo(size.width * .83, size.height * .56, size.width * .96,
          size.height * .20);
    canvas.drawPath(
        path,
        Paint()
          ..color = VoltColors.cyan.withValues(alpha: .28)
          ..strokeWidth = 13
          ..style = PaintingStyle.stroke
          ..strokeCap = StrokeCap.round);
    canvas.drawPath(
        path,
        Paint()
          ..color = VoltColors.cyan
          ..strokeWidth = 3
          ..style = PaintingStyle.stroke
          ..strokeCap = StrokeCap.round);
    for (final p in [
      Offset(size.width * .08, size.height * .73),
      Offset(size.width * .53, size.height * .48),
      Offset(size.width * .94, size.height * .22)
    ]) {
      canvas.drawCircle(
          p,
          6,
          Paint()
            ..color =
                p.dx == size.width * .53 ? VoltColors.lime : VoltColors.cyan);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class PitstopCard extends StatelessWidget {
  const PitstopCard({super.key, required this.vendor, required this.onTap});
  final Pitstop vendor;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    final isCharging = vendor.matchesDiscoveryCategory('EV Charging');
    return InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(18),
        child: VoltCard(
            padding: EdgeInsets.zero,
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (vendor.imageUrl != null &&
                  vendor.imageUrl!.startsWith('http'))
                ClipRRect(
                    borderRadius:
                        const BorderRadius.vertical(top: Radius.circular(16)),
                    child: Image.network(vendor.imageUrl!,
                        height: 145,
                        width: double.infinity,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => _vendorImage(vendor)))
              else
                _vendorImage(vendor),
              Padding(
                  padding: const EdgeInsets.all(15),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(children: [
                          Expanded(
                              child: Text(vendor.name,
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w900,
                                      fontSize: 17))),
                          Text(
                              vendor.distanceKm > 0
                                  ? '${vendor.distanceKm.toStringAsFixed(0)} km'
                                  : 'Distance unavailable',
                              style: const TextStyle(
                                  color: VoltColors.cyan,
                                  fontWeight: FontWeight.w700))
                        ]),
                        const SizedBox(height: 4),
                        Text(_serviceName(vendor.type),
                            style: const TextStyle(
                                color: VoltColors.cyan,
                                fontSize: 12,
                                fontWeight: FontWeight.w700)),
                        const SizedBox(height: 5),
                        Text(vendor.address,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(color: VoltColors.muted)),
                        const SizedBox(height: 9),
                        Wrap(spacing: 7, runSpacing: 6, children: [
                          _ServiceChip(
                              label: vendor.isVerified == true
                                  ? 'Verified partner'
                                  : 'Partner listing'),
                          if (isCharging)
                            const _ServiceChip(
                                label: 'Live connector status unavailable'),
                        ]),
                        const SizedBox(height: 12),
                        Wrap(
                            spacing: 7,
                            runSpacing: 7,
                            children: vendor.services.isEmpty
                                ? [
                                    const _ServiceChip(
                                        label: 'Charging & rest stop')
                                  ]
                                : vendor.services
                                    .map((s) => _ServiceChip(
                                        label: _serviceName(
                                            '${s['service_type'] ?? 'service'}')))
                                    .toList()),
                        const SizedBox(height: 10),
                        Row(children: [
                          const Icon(Icons.schedule_rounded,
                              size: 15, color: VoltColors.muted),
                          const SizedBox(width: 5),
                          Text(
                              vendor.availableSlotCount > 0
                                  ? '${vendor.availableSlotCount} booking slots listed'
                                  : 'Booking times shown in details',
                              style: const TextStyle(
                                  color: VoltColors.muted, fontSize: 12))
                        ]),
                        if (isCharging)
                          const Padding(
                            padding: EdgeInsets.only(top: 5),
                            child: Text(
                              'Slot listings do not confirm a charger is free right now.',
                              style: TextStyle(
                                  color: VoltColors.muted, fontSize: 10),
                            ),
                          ),
                        const SizedBox(height: 13),
                        Row(children: [
                          Expanded(
                              child: Text(
                                  vendor.startingPrice == null
                                      ? 'Partner pricing in details'
                                      : 'Partner-listed from ₹${vendor.startingPrice!.toStringAsFixed(0)}',
                                  style: const TextStyle(
                                      color: VoltColors.green,
                                      fontWeight: FontWeight.w800))),
                          FilledButton(
                              onPressed: onTap, child: const Text('View stop'))
                        ]),
                      ])),
            ])));
  }
}

Widget _vendorImage(Pitstop vendor) => Container(
      height: 112,
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 18),
      decoration: const BoxDecoration(
        color: VoltColors.elevated,
        borderRadius:
            BorderRadius.vertical(top: Radius.circular(VoltRadii.card)),
      ),
      child: Row(children: [
        Container(
          width: 44,
          height: 44,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: VoltColors.lime,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Icon(
            vendor.type.toLowerCase().contains('hotel')
                ? Icons.hotel_outlined
                : Icons.ev_station_outlined,
            size: 22,
            color: VoltColors.forest,
          ),
        ),
        const SizedBox(width: 13),
        Expanded(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('NH–16  /  ${_serviceName(vendor.type).toUpperCase()}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      color: VoltColors.muted,
                      fontWeight: FontWeight.w700,
                      fontSize: 9,
                      letterSpacing: 0.8)),
              const SizedBox(height: 5),
              Text(vendor.address,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      color: VoltColors.forest,
                      fontSize: 14,
                      fontWeight: FontWeight.w700)),
            ],
          ),
        ),
      ]),
    );

class _ServiceChip extends StatelessWidget {
  const _ServiceChip({required this.label});
  final String label;
  @override
  Widget build(BuildContext context) => Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
      decoration: BoxDecoration(
          color: VoltColors.elevated,
          borderRadius: BorderRadius.circular(7),
          border: Border.all(color: VoltColors.border)),
      child: Text(label,
          style: const TextStyle(fontSize: 11, color: VoltColors.text)));
}

String _serviceName(String value) => value
    .replaceAll('_', ' ')
    .split(' ')
    .map((word) =>
        word.isEmpty ? word : '${word[0].toUpperCase()}${word.substring(1)}')
    .join(' ');

IconData _serviceIcon(String value) {
  final type = value.toLowerCase().replaceAll(' ', '_');
  if (type.contains('room') || type.contains('hotel') || type == 'stay') {
    return Icons.hotel_rounded;
  }
  if (type.contains('food') || type.contains('restaurant')) {
    return Icons.restaurant_rounded;
  }
  if (type.contains('rest') || type.contains('lounge')) {
    return Icons.weekend_rounded;
  }
  if (type.contains('charge') || type == 'ev') return Icons.ev_station_rounded;
  return Icons.local_offer_outlined;
}

List<Pitstop> _routePitstops(Map<String, dynamic>? data) {
  final items = data?['recommended_pitstops'];
  if (items is! List) return const [];
  return items
      .whereType<Map>()
      .map((item) => Pitstop.fromJson(Map<String, dynamic>.from(item)))
      .where((item) => item.id.isNotEmpty)
      .toList(growable: false);
}

IconData _pitstopIcon(Pitstop vendor) {
  if (vendor.matchesDiscoveryCategory('Hotels')) return Icons.hotel_rounded;
  if (vendor.matchesDiscoveryCategory('Food')) return Icons.restaurant_rounded;
  return Icons.ev_station_rounded;
}

Color _pitstopColor(Pitstop vendor) {
  if (vendor.matchesDiscoveryCategory('Hotels')) return VoltColors.cyan;
  if (vendor.matchesDiscoveryCategory('Food')) return VoltColors.green;
  return VoltColors.forest;
}

class DiscoveryScreen extends StatefulWidget {
  const DiscoveryScreen({
    super.key,
    required this.app,
    this.isActive = true,
  });
  final AppController app;
  final bool isActive;
  @override
  State<DiscoveryScreen> createState() => _DiscoveryScreenState();
}

class _DiscoveryScreenState extends State<DiscoveryScreen>
    with WidgetsBindingObserver {
  late Future<List<Pitstop>> _vendors;
  StreamSubscription<void>? _catalogChanges;
  StreamSubscription<Position>? _positionSubscription;
  Timer? _refreshDebounce;
  String _filter = 'All';
  String _query = '';
  bool _map = true;
  bool _nearbyAlertsEnabled = false;
  bool _startingNearbyAlerts = false;
  bool _refreshingForAlerts = false;
  bool _appIsResumed = true;
  String? _nearbyAlertMessage;
  LatLng? _searchCenter;
  LatLng? _lastAlertLookupPoint;
  DateTime? _lastAlertLookupAt;
  List<Pitstop> _nearbyAlertStations = const [];
  final Map<String, DateTime> _recentlyAlertedStations = {};

  void _searchMapArea(LatLng center) {
    _searchCenter = center;
    setState(() {
      _vendors = widget.app.driverRepository.nearbyPitstops(
        lat: center.latitude,
        lng: center.longitude,
        radiusKm: 50,
      );
    });
  }

  final _filters = const ['All', 'EV Charging', 'Food', 'Hotels'];
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    final repository = widget.app.driverRepository;
    _vendors = repository.nearbyPitstops();
    _catalogChanges = repository.watchPitstopDirectoryChanges().listen(
          (_) => _scheduleRefresh(),
          onError: (_) {},
        );
  }

  void _scheduleRefresh() {
    _refreshDebounce?.cancel();
    _refreshDebounce = Timer(const Duration(milliseconds: 180), () {
      if (mounted) {
        setState(() {
          _vendors = widget.app.driverRepository.nearbyPitstops(
            lat: _searchCenter?.latitude ?? AppConfig.discoveryFallbackLat,
            lng: _searchCenter?.longitude ?? AppConfig.discoveryFallbackLng,
            radiusKm: 50,
          );
        });
      }
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _refreshDebounce?.cancel();
    _catalogChanges?.cancel();
    _positionSubscription?.cancel();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant DiscoveryScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.isActive && !widget.isActive && _nearbyAlertsEnabled) {
      unawaited(
          _pauseNearbyAlerts('Nearby alerts pause when you leave Explore.'));
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _appIsResumed = state == AppLifecycleState.resumed;
    if (state != AppLifecycleState.resumed && _nearbyAlertsEnabled) {
      unawaited(_pauseNearbyAlerts(
          'Nearby alerts pause when VoltStop is in the background.'));
    }
  }

  Future<void> _pauseNearbyAlerts(String message) async {
    await _positionSubscription?.cancel();
    _positionSubscription = null;
    if (mounted) {
      setState(() {
        _nearbyAlertsEnabled = false;
        _nearbyAlertMessage = message;
      });
    }
  }

  Future<LatLng> _getCurrentPoint() async {
    if (!await Geolocator.isLocationServiceEnabled()) {
      throw const _LocationFailure(
          'Turn on location services to use nearby alerts.');
    }
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.deniedForever) {
      throw const _LocationFailure(
          'Location is blocked for VoltStop. Enable it in app settings to use nearby alerts.');
    }
    if (permission == LocationPermission.denied) {
      throw const _LocationFailure(
          'Allow location access to use nearby alerts.');
    }
    final position = await Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.medium,
        timeLimit: Duration(seconds: 12),
      ),
    );
    return LatLng(position.latitude, position.longitude);
  }

  Future<void> _toggleNearbyAlerts(bool enabled) async {
    if (!enabled) {
      await _positionSubscription?.cancel();
      _positionSubscription = null;
      if (mounted) {
        setState(() {
          _nearbyAlertsEnabled = false;
          _nearbyAlertMessage = 'Nearby alerts are paused.';
        });
      }
      return;
    }
    if (!widget.isActive || !_appIsResumed) return;
    if (_startingNearbyAlerts || _nearbyAlertsEnabled) return;
    setState(() {
      _startingNearbyAlerts = true;
      _nearbyAlertMessage = null;
    });
    try {
      final point = await _getCurrentPoint();
      final stations = await widget.app.driverRepository.nearbyPitstops(
        lat: point.latitude,
        lng: point.longitude,
        radiusKm: 50,
      );
      if (!mounted || !widget.isActive || !_appIsResumed) return;
      _searchCenter = point;
      _lastAlertLookupPoint = point;
      _lastAlertLookupAt = DateTime.now();
      setState(() {
        _vendors = Future.value(stations);
        _nearbyAlertStations = stations;
        _nearbyAlertsEnabled = true;
        _nearbyAlertMessage = _nearbyAlertCoverageMessage(point, stations);
      });
      _showNearestChargingAlert(point);
      _positionSubscription = Geolocator.getPositionStream(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.medium,
          distanceFilter: 1000,
        ),
      ).listen(_onAlertPosition, onError: (_) {
        unawaited(_pauseNearbyAlerts(
            'Location updates stopped. Nearby alerts are paused.'));
      });
    } on _LocationFailure catch (error) {
      if (mounted) setState(() => _nearbyAlertMessage = error.message);
    } on LocationServiceDisabledException {
      if (mounted) {
        setState(() => _nearbyAlertMessage =
            'Location services are off. Turn them on to use nearby alerts.');
      }
    } on PermissionDefinitionsNotFoundException {
      if (mounted) {
        setState(() => _nearbyAlertMessage =
            'This app build has no location permission description.');
      }
    } catch (_) {
      if (mounted) {
        setState(() => _nearbyAlertMessage =
            'Could not load nearby charging stops. Check your connection and retry.');
      }
    } finally {
      if (mounted) setState(() => _startingNearbyAlerts = false);
    }
  }

  Future<void> _onAlertPosition(Position position) async {
    if (!widget.isActive || !_appIsResumed || !_nearbyAlertsEnabled) return;
    final now = DateTime.now();
    final previous = _lastAlertLookupPoint;
    final movedMeters = previous == null
        ? double.infinity
        : Geolocator.distanceBetween(previous.latitude, previous.longitude,
            position.latitude, position.longitude);
    final lookupIsDue = previous == null ||
        movedMeters >= 10000 ||
        now.difference(_lastAlertLookupAt ?? DateTime(2000)) >=
            const Duration(minutes: 10);
    if (lookupIsDue && !_refreshingForAlerts) {
      _refreshingForAlerts = true;
      try {
        final stations = await widget.app.driverRepository.nearbyPitstops(
          lat: position.latitude,
          lng: position.longitude,
          radiusKm: 50,
        );
        _nearbyAlertStations = stations;
        _lastAlertLookupPoint = LatLng(position.latitude, position.longitude);
        _lastAlertLookupAt = now;
        _searchCenter = _lastAlertLookupPoint;
        if (mounted) {
          setState(() {
            _vendors = Future.value(stations);
            _nearbyAlertMessage =
                _nearbyAlertCoverageMessage(_lastAlertLookupPoint!, stations);
          });
        }
      } catch (_) {
        // Keep the last successful nearby results while connectivity recovers.
      } finally {
        _refreshingForAlerts = false;
      }
    }

    _showNearestChargingAlert(LatLng(position.latitude, position.longitude));
  }

  String _nearbyAlertCoverageMessage(LatLng point, List<Pitstop> stations) {
    final chargingStops = stations
        .where((vendor) =>
            vendor.matchesDiscoveryCategory('EV Charging') &&
            vendor.lat != null &&
            vendor.lng != null)
        .map((vendor) => MapEntry(
            vendor,
            Geolocator.distanceBetween(
                point.latitude, point.longitude, vendor.lat!, vendor.lng!)))
        .toList()
      ..sort((a, b) => a.value.compareTo(b.value));

    if (chargingStops.isEmpty) {
      return 'Alerts are on, but no approved partner-listed charging stops were found within 50 km. Stops appear after a vendor is approved and adds a map location. Alerts are in-app while Explore stays open.';
    }
    final nearest = chargingStops.first;
    final distanceKm = nearest.value / 1000;
    if (distanceKm <= 5) {
      return 'Alerts are on. ${nearest.key.name} is within 5 km. Charger availability is based on partner listings, not live plug data.';
    }
    return 'Alerts are on. ${nearest.key.name} is ${distanceKm.toStringAsFixed(1)} km away; an in-app alert appears within 5 km. Explore must stay open.';
  }

  void _showNearestChargingAlert(LatLng point) {
    final now = DateTime.now();
    if (!_nearbyAlertsEnabled) return;
    final candidates = _nearbyAlertStations
        .where((vendor) =>
            vendor.matchesDiscoveryCategory('EV Charging') &&
            vendor.lat != null &&
            vendor.lng != null)
        .map((vendor) => MapEntry(
            vendor,
            Geolocator.distanceBetween(
                point.latitude, point.longitude, vendor.lat!, vendor.lng!)))
        .where((entry) => entry.value <= 5000)
        .toList()
      ..sort((a, b) => a.value.compareTo(b.value));
    if (candidates.isEmpty || !mounted) return;
    final nearest = candidates.first;
    final lastAlert = _recentlyAlertedStations[nearest.key.id];
    if (lastAlert != null &&
        now.difference(lastAlert) < const Duration(minutes: 45)) {
      return;
    }
    _recentlyAlertedStations[nearest.key.id] = now;
    _recentlyAlertedStations.removeWhere(
        (_, time) => now.difference(time) > const Duration(hours: 2));
    final distanceKm = nearest.value / 1000;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: Text(
            '${nearest.key.name} is ${distanceKm.toStringAsFixed(1)} km away. Live charger status is not available.'),
        duration: const Duration(seconds: 6),
      ));
  }

  bool _matches(Pitstop vendor) {
    final haystack =
        '${vendor.name} ${vendor.type} ${vendor.address} ${vendor.services.map((s) => s['service_type']).join(' ')}'
            .toLowerCase();
    final queryMatches = haystack.contains(_query.toLowerCase());
    final categoryMatches = vendor.matchesDiscoveryCategory(_filter);
    return queryMatches && categoryMatches;
  }

  @override
  Widget build(BuildContext context) => CustomScrollView(slivers: [
        SliverPadding(
            padding: const EdgeInsets.fromLTRB(18, 15, 18, 20),
            sliver: SliverList(
                delegate: SliverChildListDelegate([
              const BrandMark(compact: true),
              const SizedBox(height: 20),
              const VoltPageHeading(
                eyebrow: 'Explore the corridor',
                title: 'Find your next stop',
                subtitle: 'Places to charge, eat and rest along the way.',
              ),
              const SizedBox(height: 12),
              Text(
                'Charging points are partner listings. Live connector availability is not yet linked to a charge-network provider.',
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: VoltColors.muted),
              ),
              const SizedBox(height: 17),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                decoration: BoxDecoration(
                  color: VoltColors.forest,
                  borderRadius: BorderRadius.circular(VoltRadii.control),
                ),
                child: const Row(children: [
                  VoltIconBadge(icon: Icons.route_rounded, size: 36),
                  SizedBox(width: 11),
                  Expanded(
                    child: Text(
                        'NH–16 pilot corridor\nSrikakulam  ·  Vijayawada',
                        style: TextStyle(
                            color: VoltColors.surface,
                            fontSize: 12,
                            height: 1.45,
                            fontWeight: FontWeight.w600)),
                  ),
                  Icon(Icons.bolt_rounded, color: VoltColors.lime, size: 20),
                ]),
              ),
              const SizedBox(height: 10),
              VoltCard(
                padding: const EdgeInsets.fromLTRB(13, 8, 9, 8),
                child: Row(children: [
                  Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      color: VoltColors.elevated,
                      borderRadius: BorderRadius.circular(11),
                    ),
                    child: const Icon(Icons.notifications_active_outlined,
                        color: VoltColors.forest, size: 19),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Nearby charger alerts',
                            style: Theme.of(context).textTheme.titleSmall),
                        Text(
                          _nearbyAlertsEnabled
                              ? 'In-app alerts · within 5 km · Explore open'
                              : 'In-app only · Explore must stay open',
                          style: Theme.of(context)
                              .textTheme
                              .bodySmall
                              ?.copyWith(color: VoltColors.muted),
                        ),
                      ],
                    ),
                  ),
                  if (_startingNearbyAlerts)
                    const Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                    )
                  else
                    Switch.adaptive(
                      value: _nearbyAlertsEnabled,
                      onChanged: _toggleNearbyAlerts,
                    ),
                ]),
              ),
              if (_nearbyAlertMessage != null)
                Padding(
                  padding: const EdgeInsets.fromLTRB(5, 7, 5, 0),
                  child: Text(_nearbyAlertMessage!,
                      style: Theme.of(context)
                          .textTheme
                          .bodySmall
                          ?.copyWith(color: VoltColors.muted)),
                ),
              const SizedBox(height: 12),
              TextField(
                  onChanged: (value) => setState(() => _query = value),
                  decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.search),
                      hintText: 'Search pitstops, food, stays…',
                      suffixIcon: Icon(Icons.tune))),
              const SizedBox(height: 12),
              SizedBox(
                  height: 42,
                  child: ListView(
                      scrollDirection: Axis.horizontal,
                      children: _filters
                          .map((filter) => Padding(
                              padding: const EdgeInsets.only(right: 8),
                              child: ChoiceChip(
                                  label: Text(filter),
                                  selected: _filter == filter,
                                  onSelected: (_) =>
                                      setState(() => _filter = filter))))
                          .toList())),
              const SizedBox(height: 14),
              LayoutBuilder(builder: (context, constraints) {
                final title = Text(
                  'Stops in this area',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.titleMedium,
                );
                final mapToggle = TextButton.icon(
                  onPressed: () => setState(() => _map = !_map),
                  icon: Icon(_map ? Icons.map_outlined : Icons.map),
                  label: Text(_map ? 'Hide map' : 'Show map'),
                );
                final largeText =
                    MediaQuery.textScalerOf(context).scale(14) > 16;
                if (constraints.maxWidth < 390 || largeText) {
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      title,
                      Align(alignment: Alignment.centerRight, child: mapToggle),
                    ],
                  );
                }
                return Row(children: [Expanded(child: title), mapToggle]);
              }),
              if (_map)
                SizedBox(
                    height: 330,
                    child: _DiscoveryMap(
                        future: _vendors
                            .then((items) => items.where(_matches).toList()),
                        onSearchArea: _searchMapArea))
              else
                const SizedBox.shrink(),
              const SizedBox(height: 8),
              FutureBuilder<List<Pitstop>>(
                  future: _vendors,
                  builder: (context, snapshot) {
                    if (snapshot.connectionState == ConnectionState.waiting)
                      return const VoltLoading(label: 'Loading pitstops…');
                    if (snapshot.hasError)
                      return VoltError(
                          message: '${snapshot.error}',
                          onRetry: () {
                            setState(() {
                              _vendors =
                                  widget.app.driverRepository.nearbyPitstops();
                            });
                          });
                    final vendors = snapshot.data!.where(_matches).toList();
                    if (vendors.isEmpty)
                      return const VoltCard(
                          child: Text(
                              'No places match this category yet. Try another category or radius.',
                              style: TextStyle(color: VoltColors.muted)));
                    return Column(
                        children: vendors
                            .map((v) => Padding(
                                padding: const EdgeInsets.only(bottom: 13),
                                child: PitstopCard(
                                    vendor: v,
                                    onTap: () => Navigator.push(
                                        context,
                                        MaterialPageRoute(
                                            builder: (_) =>
                                                PitstopDetailsScreen(
                                                    app: widget.app,
                                                    vendorId: v.id))))))
                            .toList());
                  }),
            ]))),
      ]);
}

class _DiscoveryMap extends StatefulWidget {
  const _DiscoveryMap({required this.future, required this.onSearchArea});
  final Future<List<Pitstop>> future;
  final ValueChanged<LatLng> onSearchArea;
  @override
  State<_DiscoveryMap> createState() => _DiscoveryMapState();
}

class _DiscoveryMapState extends State<_DiscoveryMap> {
  final MapController _controller = MapController();
  LatLng? _selectedPoint;
  LatLng? _devicePoint;
  String? _locationMessage;
  bool _mapReady = false;
  bool _locating = false;

  Future<void> _useCurrentLocation() async {
    setState(() {
      _locating = true;
      _locationMessage = null;
    });
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        throw const _LocationFailure(
            'Turn on location services to use this control.');
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.deniedForever) {
        throw const _LocationFailure(
            'Location permission is disabled for VoltStop. Change it in app settings, or choose an area on the map.');
      }
      if (permission == LocationPermission.denied) {
        throw const _LocationFailure(
            'Location permission was denied. Choose an area on the map instead.');
      }
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.medium,
          timeLimit: Duration(seconds: 12),
        ),
      );
      if (!mounted) return;
      final point = LatLng(position.latitude, position.longitude);
      setState(() {
        _devicePoint = point;
        _selectedPoint = point;
      });
      if (_mapReady) _controller.move(point, 13);
      widget.onSearchArea(point);
    } on _LocationFailure catch (error) {
      if (mounted) setState(() => _locationMessage = error.message);
    } on LocationServiceDisabledException {
      if (mounted)
        setState(() => _locationMessage =
            'Location services are off. You can still choose an area on the map.');
    } on PermissionDefinitionsNotFoundException {
      if (mounted)
        setState(() => _locationMessage =
            'This app build has no location permission description. You can still choose an area on the map.');
    } catch (_) {
      if (mounted)
        setState(() => _locationMessage =
            'Your current location could not be found. Choose an area on the map instead.');
    } finally {
      if (mounted) setState(() => _locating = false);
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<List<Pitstop>>(
      future: widget.future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting)
          return const VoltCard(
              child: SizedBox(
                  height: 280,
                  child: Center(child: CircularProgressIndicator())));
        if (snapshot.hasError)
          return VoltCard(
              child: SizedBox(
                  height: 280,
                  child: Center(
                      child: Text(
                          'Map locations are unavailable. Refresh the pitstop list to try again.',
                          textAlign: TextAlign.center,
                          style: const TextStyle(color: VoltColors.muted)))));
        final vendors = snapshot.data ?? const <Pitstop>[];
        final valid =
            vendors.where((v) => v.lat != null && v.lng != null).toList();
        if (valid.isEmpty)
          return const VoltCard(
              child: SizedBox(
                  height: 280,
                  child: Center(
                      child: Text(
                          'No map locations are available yet. You can keep browsing the list.',
                          textAlign: TextAlign.center))));
        final markers = valid
            .map((v) => Marker(
                  point: LatLng(v.lat!, v.lng!),
                  width: 36,
                  height: 36,
                  child: Tooltip(
                      message: v.name,
                      child: Icon(_pitstopIcon(v),
                          color: _pitstopColor(v), size: 28)),
                ))
            .toList();
        if (_selectedPoint != null) {
          markers.add(Marker(
            point: _selectedPoint!,
            width: 32,
            height: 32,
            child: Semantics(
                label: _devicePoint == _selectedPoint
                    ? 'Your current location'
                    : 'Selected search area',
                child: Container(
                    decoration: BoxDecoration(
                        color: VoltColors.forest.withValues(alpha: .86),
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 3)),
                    child: const Icon(Icons.my_location,
                        size: 16, color: Colors.white))),
          ));
        }
        return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(children: [
                const Expanded(
                    child: Text(
                        'Choose an area on the map, or use your location to find nearby places.',
                        style:
                            TextStyle(color: VoltColors.muted, fontSize: 11))),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                    onPressed: _locating ? null : _useCurrentLocation,
                    icon: _locating
                        ? const SizedBox(
                            width: 15,
                            height: 15,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.my_location, size: 16),
                    label: Text(_locating ? 'Locating…' : 'My location')),
              ]),
              if (_locationMessage != null)
                Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(_locationMessage!,
                        style: const TextStyle(
                            color: VoltColors.warning, fontSize: 11))),
              const SizedBox(height: 6),
              Expanded(
                  child: ClipRRect(
                borderRadius: BorderRadius.circular(18),
                child: Stack(children: [
                  FlutterMap(
                    mapController: _controller,
                    options: MapOptions(
                      initialCenter: LatLng(valid.first.lat!, valid.first.lng!),
                      initialZoom: 7,
                      onMapReady: () => _mapReady = true,
                      onTap: (_, point) =>
                          setState(() => _selectedPoint = point),
                    ),
                    children: [
                      TileLayer(
                          urlTemplate: AppConfig.osmTileUrl,
                          userAgentPackageName: 'com.voltstop.app'),
                      MarkerLayer(markers: markers),
                      RichAttributionWidget(attributions: [
                        TextSourceAttribution('OpenStreetMap contributors',
                            onTap: () => launchUrl(Uri.parse(
                                'https://openstreetmap.org/copyright'))),
                      ]),
                    ],
                  ),
                  if (_selectedPoint != null)
                    Positioned(
                        left: 10,
                        bottom: 10,
                        child: FilledButton.icon(
                          onPressed: () => widget.onSearchArea(_selectedPoint!),
                          icon: const Icon(Icons.search, size: 17),
                          label: const Text('Search this area'),
                        )),
                ]),
              )),
            ]);
      });
}

String _formatRouteDuration(int seconds) {
  final minutes = (seconds / 60).round();
  final hours = minutes ~/ 60;
  final remainder = minutes % 60;
  if (hours == 0) return '$remainder min';
  if (remainder == 0) return '$hours hr';
  return '$hours hr $remainder min';
}

class _LocationFailure implements Exception {
  const _LocationFailure(this.message);
  final String message;
}

class PitstopDetailsScreen extends StatefulWidget {
  const PitstopDetailsScreen(
      {super.key, required this.app, required this.vendorId});
  final AppController app;
  final String vendorId;
  @override
  State<PitstopDetailsScreen> createState() => _PitstopDetailsScreenState();
}

class _PitstopDetailsScreenState extends State<PitstopDetailsScreen> {
  late Future<List<dynamic>> _load;
  StreamSubscription<void>? _pitstopChanges;
  Timer? _refreshDebounce;
  Timer? _fallbackRefresh;

  @override
  void initState() {
    super.initState();
    _load = _fetch();
    _pitstopChanges = widget.app.driverRepository
        .watchPitstopChanges(widget.vendorId)
        .listen((_) => _scheduleRefresh(), onError: (_) {});
    _fallbackRefresh = Timer.periodic(
      const Duration(seconds: 30),
      (_) => _scheduleRefresh(),
    );
  }

  Future<List<dynamic>> _fetch() => Future.wait([
        widget.app.driverRepository.pitstop(widget.vendorId),
        widget.app.driverRepository.slots(widget.vendorId)
      ]);

  void _scheduleRefresh() {
    _refreshDebounce?.cancel();
    _refreshDebounce = Timer(const Duration(milliseconds: 180), () {
      if (mounted) setState(() => _load = _fetch());
    });
  }

  @override
  void dispose() {
    _refreshDebounce?.cancel();
    _fallbackRefresh?.cancel();
    _pitstopChanges?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: const Text('Pitstop details'), actions: [
        IconButton(
            tooltip: 'Refresh pitstop details',
            onPressed: _scheduleRefresh,
            icon: const Icon(Icons.refresh_rounded))
      ]),
      body: FutureBuilder<List<dynamic>>(
          future: _load,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting)
              return const VoltLoading(label: 'Loading pitstop details…');
            if (snapshot.hasError)
              return Center(
                  child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: VoltError(
                          message: '${snapshot.error}',
                          onRetry: () {
                            setState(() => _load = _fetch());
                          })));
            final vendor = snapshot.data![0] as Pitstop;
            final slots = snapshot.data![1] as List<Map<String, dynamic>>;
            final isHotel = vendor.type.toLowerCase() == 'hotel';
            final customerSlots = isHotel
                ? slots.where((slot) {
                    final service = '${slot['service_type'] ?? ''}'
                        .toLowerCase()
                        .replaceAll(' ', '_');
                    return service.contains('charg') || service == 'ev';
                  }).toList()
                : slots;
            return ListView(
                padding: const EdgeInsets.fromLTRB(18, 4, 18, 100),
                children: [
                  if (vendor.imageUrl != null &&
                      vendor.imageUrl!.startsWith('http'))
                    ClipRRect(
                        borderRadius: BorderRadius.circular(18),
                        child: Image.network(vendor.imageUrl!,
                            height: 210,
                            width: double.infinity,
                            fit: BoxFit.cover,
                            errorBuilder: (_, __, ___) => _vendorImage(vendor)))
                  else
                    _vendorImage(vendor),
                  const SizedBox(height: 14),
                  Row(children: [
                    Expanded(
                        child: Text(vendor.name,
                            style: Theme.of(context)
                                .textTheme
                                .headlineSmall
                                ?.copyWith(fontWeight: FontWeight.w900))),
                    if (vendor.isVerified == true)
                      const Icon(Icons.verified, color: VoltColors.green)
                  ]),
                  const SizedBox(height: 6),
                  Text(vendor.address,
                      style: const TextStyle(color: VoltColors.muted)),
                  const SizedBox(height: 8),
                  Wrap(spacing: 8, children: [
                    Chip(label: Text(_serviceName(vendor.type))),
                    if (vendor.isVerified == true)
                      const Chip(
                          avatar: Icon(Icons.verified,
                              color: VoltColors.green, size: 16),
                          label: Text('Verified'))
                  ]),
                  const SizedBox(height: 18),
                  if (vendor.type.toLowerCase() == 'hotel') ...[
                    SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                            onPressed: () => Navigator.push(
                                context,
                                MaterialPageRoute(
                                    builder: (_) => HotelBookingScreen(
                                        app: widget.app, vendor: vendor))),
                            icon: const Icon(Icons.hotel_rounded),
                            label:
                                const Text('Choose dates & reserve a room'))),
                    const SizedBox(height: 18),
                  ],
                  if (vendor.type.toLowerCase() == 'restaurant') ...[
                    SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                          onPressed: () => Navigator.push(
                              context,
                              MaterialPageRoute(
                                  builder: (_) => RestaurantMenuScreen(
                                      app: widget.app, vendor: vendor))),
                          icon: const Icon(Icons.restaurant_menu_rounded),
                          label: const Text('Browse menu & order'),
                        )),
                    const SizedBox(height: 18),
                  ],
                  const Text('Services offered',
                      style:
                          TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
                  const SizedBox(height: 10),
                  VoltCard(
                      child: vendor.services.isEmpty
                          ? const Text(
                              'No service details have been published.',
                              style: TextStyle(color: VoltColors.muted))
                          : Column(
                              children: vendor.services
                                  .map((s) => ListTile(
                                      contentPadding: EdgeInsets.zero,
                                      leading: Icon(
                                          _serviceIcon(
                                              '${s['service_type'] ?? ''}'),
                                          color: _serviceIcon(
                                                      '${s['service_type'] ?? ''}') ==
                                                  Icons.hotel_rounded
                                              ? VoltColors.cyan
                                              : VoltColors.green),
                                      title: Text(_serviceName(
                                          '${s['service_type'] ?? 'Service'}')),
                                      trailing: Text(
                                          s['price_inr'] == null
                                              ? 'Price not listed'
                                              : '₹${s['price_inr']}',
                                          style: const TextStyle(
                                              color: VoltColors.green,
                                              fontWeight: FontWeight.w700))))
                                  .toList())),
                  if (vendor.description?.isNotEmpty ?? false) ...[
                    const SizedBox(height: 16),
                    const Text('About',
                        style: TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 17)),
                    const SizedBox(height: 8),
                    Text(vendor.description!,
                        style: const TextStyle(color: VoltColors.muted))
                  ],
                  if (customerSlots.isNotEmpty) ...[
                  const SizedBox(height: 20),
                  Row(children: [
                    const Expanded(
                        child: Text('Available time slots',
                            style: TextStyle(
                                fontWeight: FontWeight.w800, fontSize: 17))),
                    Text('${customerSlots.length} available',
                        style: const TextStyle(color: VoltColors.green))
                  ]),
                  const SizedBox(height: 10),
                  ...customerSlots.take(3).map((slot) => Padding(
                        padding: const EdgeInsets.only(bottom: 9),
                        child: _SlotTile(
                            slot: slot, showSelect: false, onSelect: () {}))),
                  if (customerSlots.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                            onPressed: () => Navigator.push(
                                context,
                                MaterialPageRoute(
                                    builder: (_) => SlotSelectionScreen(
                                        app: widget.app,
                                        vendor: vendor,
                                        slots: customerSlots))),
                            icon: const Icon(Icons.schedule),
                            label: const Text('Select Slot')))
                  ],
                  ],
                ]);
          }));
}

class HotelBookingScreen extends StatefulWidget {
  const HotelBookingScreen(
      {super.key, required this.app, required this.vendor});
  final AppController app;
  final Pitstop vendor;

  @override
  State<HotelBookingScreen> createState() => _HotelBookingScreenState();
}

class _HotelBookingScreenState extends State<HotelBookingScreen> {
  final Razorpay _razorpay = Razorpay();
  late DateTime _checkIn;
  late DateTime _checkOut;
  TimeOfDay _checkInTime = const TimeOfDay(hour: 14, minute: 0);
  TimeOfDay _checkOutTime = const TimeOfDay(hour: 11, minute: 0);
  late Future<List<Map<String, dynamic>>> _rooms;
  int _guests = 2;
  int _roomCount = 1;
  bool _busy = false;
  bool _checking = false;
  String? _reservationId;
  String? _razorpayOrderId;
  String? _statusMessage;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _checkIn = DateUtils.dateOnly(DateTime.now().add(const Duration(days: 1)));
    _checkOut = _checkIn.add(const Duration(days: 1));
    _rooms = _loadRooms();
    _razorpay.on(Razorpay.EVENT_PAYMENT_SUCCESS, _onPaymentSuccess);
    _razorpay.on(Razorpay.EVENT_PAYMENT_ERROR, (_) => _checkStatus());
    _razorpay.on(Razorpay.EVENT_EXTERNAL_WALLET, (_) => _checkStatus());
  }

  Future<List<Map<String, dynamic>>> _loadRooms() =>
      widget.app.driverRepository.hotelRooms(
          vendorId: widget.vendor.id,
          checkIn: _checkIn,
          checkOut: _checkOut,
          guests: _guests,
          rooms: _roomCount,
          checkInTime: _timeValue(_checkInTime),
          checkOutTime: _timeValue(_checkOutTime));

  @override
  void dispose() {
    _poll?.cancel();
    _razorpay.clear();
    super.dispose();
  }

  Future<void> _chooseDate({required bool arrival}) async {
    final today = DateUtils.dateOnly(DateTime.now());
    final initial = arrival ? _checkIn : _checkOut;
    final value = await showDatePicker(
        context: context,
        initialDate: initial.isBefore(today) ? today : initial,
        firstDate: today,
        lastDate: today.add(const Duration(days: 365)));
    if (value == null || !mounted) return;
    setState(() {
      if (arrival) {
        _checkIn = value;
        if (!_checkOut.isAfter(value))
          _checkOut = value.add(const Duration(days: 1));
      } else {
        if (value.isAfter(_checkIn)) _checkOut = value;
      }
      _rooms = _loadRooms();
    });
  }

  String _timeValue(TimeOfDay time) =>
      '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';

  Future<void> _chooseTime({required bool arrival}) async {
    final selected = await showTimePicker(
      context: context,
      initialTime: arrival ? _checkInTime : _checkOutTime,
      helpText: arrival ? 'Choose arrival time' : 'Choose departure time',
    );
    if (selected == null || !mounted) return;
    setState(() {
      if (arrival) {
        _checkInTime = selected;
      } else {
        _checkOutTime = selected;
      }
      _rooms = _loadRooms();
    });
  }

  Future<void> _reserve(Map<String, dynamic> room) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _statusMessage = null;
    });
    try {
      final quote = await widget.app.driverRepository.hotelQuote(
          roomTypeId: '${room['room_type_id']}',
          checkIn: _checkIn,
          checkOut: _checkOut,
          guests: _guests,
          rooms: _roomCount,
          checkInTime: _timeValue(_checkInTime),
          checkOutTime: _timeValue(_checkOutTime));
      if (!mounted) return;
      setState(() => _busy = false);
      final nightlyRates = (quote['nightly_rates'] as List? ?? const [])
          .whereType<Map>()
          .map((item) =>
              '${_hotelDate(item['stay_date'])}: ₹${item['rate_inr']} × $_roomCount room(s)')
          .toList();
      final accepted = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
                title: const Text('Review hotel price'),
                content: SingleChildScrollView(
                    child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                      Text('${quote['room_name']} · ${widget.vendor.name}',
                          style: const TextStyle(fontWeight: FontWeight.w800)),
                      Text(
                          '${_dateLabel(_checkIn)} – ${_dateLabel(_checkOut)} · ${quote['nights']} night(s)'),
                      Text('${_checkInTime.format(context)} arrival · ${_checkOutTime.format(context)} departure'),
                      Text('$_guests guest(s) · $_roomCount room(s)'),
                      const SizedBox(height: 10),
                      ...nightlyRates.map((line) => Padding(
                          padding: const EdgeInsets.only(bottom: 3),
                          child: Text(line))),
                      const Divider(),
                      Text('Total: ₹${quote['amount_inr']}',
                          style: const TextStyle(
                              fontSize: 18, fontWeight: FontWeight.w900)),
                      const Text(
                          'Cancellation refunds depend on how long before check-in you cancel. The exact amount is shown before you confirm.',
                          style: TextStyle(color: VoltColors.muted)),
                      const SizedBox(height: 8),
                      const Text(
                          'The server will check this exact price and availability again before creating your payment order.'),
                    ])),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(context, false),
                      child: const Text('Go back')),
                  FilledButton(
                      onPressed: () => Navigator.pop(context, true),
                      child: const Text('Continue to payment')),
                ],
              ));
      if (accepted != true || !mounted) return;
      setState(() => _busy = true);
      final key =
          'hotel-${DateTime.now().microsecondsSinceEpoch}-${room['room_type_id']}';
      final reservation = await widget.app.driverRepository
          .createHotelReservation(
              roomTypeId: '${room['room_type_id']}',
              checkIn: _checkIn,
              checkOut: _checkOut,
              guests: _guests,
              rooms: _roomCount,
              checkInTime: _timeValue(_checkInTime),
              checkOutTime: _timeValue(_checkOutTime),
              expectedAmountInr: '${quote['amount_inr']}',
              idempotencyKey: key);
      _reservationId = '${reservation['id']}';
      final payment =
          Map<String, dynamic>.from(reservation['payment'] as Map? ?? const {});
      if (payment['order_id'] == null ||
          payment['key_id'] == null ||
          payment['amount_paise'] is! num) {
        throw StateError(
            'Payment order details are unavailable. Reservation status remains on the server.');
      }
      _razorpayOrderId = '${payment['order_id']}';
      if (!mounted) return;
      setState(() {
        _busy = false;
        _statusMessage =
            'Complete payment in Razorpay. Your stay is booked only after VoltStop confirms the verified payment.';
      });
      _razorpay.open({
        'key': payment['key_id'],
        'order_id': payment['order_id'],
        'amount': (payment['amount_paise'] as num).toInt(),
        'currency': payment['currency'] ?? 'INR',
        'name': 'VoltStop',
        'description': '${room['room_name']} at ${widget.vendor.name}',
        'prefill': {'contact': widget.app.profile?.phone ?? ''},
      });
      _startStatusPolling();
    } catch (error) {
      if (mounted)
        setState(() {
          _busy = false;
          _statusMessage = '$error';
        });
    }
  }

  void _startStatusPolling() {
    _poll?.cancel();
    _poll = Timer.periodic(const Duration(seconds: 10), (_) => _checkStatus());
    _checkStatus();
  }

  Future<void> _onPaymentSuccess(PaymentSuccessResponse response) async {
    final orderId = response.orderId ?? _razorpayOrderId;
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
        // Polling remains useful if the verification request temporarily fails;
        // only the API's verified provider state can confirm the reservation.
      }
    }
    await _checkStatus();
  }

  Future<void> _checkStatus() async {
    final id = _reservationId;
    if (id == null || _checking) return;
    _checking = true;
    try {
      final reservation =
          await widget.app.driverRepository.hotelReservation(id);
      if (!mounted) return;
      final status = '${reservation['status'] ?? ''}';
      if (status == 'confirmed') {
        _poll?.cancel();
        setState(() => _statusMessage =
            'Reservation confirmed by VoltStop after verified payment.');
      } else if (status == 'expired' || status == 'cancelled') {
        _poll?.cancel();
        setState(() => _statusMessage =
            'The reservation hold ended. The server has not confirmed this stay.');
      } else if (status == 'refund_pending') {
        _poll?.cancel();
        setState(() => _statusMessage =
            'Payment was received after the room hold ended. A refund request is pending finance review; the stay is not confirmed.');
      } else if (status == 'refund_failed') {
        _poll?.cancel();
        setState(() => _statusMessage =
            'The stay was not confirmed and the refund provider reported a failure. Contact VoltStop support with this reservation ID.');
      } else {
        setState(() => _statusMessage =
            'Payment confirmation is pending. Do not pay again while VoltStop verifies the gateway event.');
      }
    } catch (_) {
      if (mounted)
        setState(() => _statusMessage =
            'Could not refresh confirmation. Check My Trips; do not pay again while verification is pending.');
    } finally {
      _checking = false;
    }
  }

  String _dateLabel(DateTime date) =>
      '${date.day.toString().padLeft(2, '0')}/${date.month.toString().padLeft(2, '0')}/${date.year}';

  String _displayTime(Object? value) {
    final raw = '${value ?? ''}';
    final parts = raw.split(':');
    if (parts.length < 2) return raw;
    final hour = int.tryParse(parts[0]);
    final minute = int.tryParse(parts[1]);
    if (hour == null || minute == null) return raw;
    return TimeOfDay(hour: hour, minute: minute).format(context);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: Text('${widget.vendor.name} · Rooms')),
      body: ListView(
          padding: const EdgeInsets.fromLTRB(18, 8, 18, 32),
          children: [
            VoltCard(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  const Text('Your stay',
                      style:
                          TextStyle(fontWeight: FontWeight.w900, fontSize: 18)),
                  const SizedBox(height: 10),
                  Row(children: [
                    Expanded(
                        child: OutlinedButton.icon(
                            onPressed: () => _chooseDate(arrival: true),
                            icon: const Icon(Icons.login),
                            label: Text('Check-in\n${_dateLabel(_checkIn)}'))),
                    const SizedBox(width: 8),
                    Expanded(
                        child: OutlinedButton.icon(
                            onPressed: () => _chooseDate(arrival: false),
                            icon: const Icon(Icons.logout),
                            label: Text('Check-out\n${_dateLabel(_checkOut)}')))
                  ]),
                  const SizedBox(height: 8),
                  Row(children: [
                    Expanded(
                        child: OutlinedButton.icon(
                            onPressed: () => _chooseTime(arrival: true),
                            icon: const Icon(Icons.schedule),
                            label: Text('Arrival · ${_checkInTime.format(context)}'))),
                    const SizedBox(width: 8),
                    Expanded(
                        child: OutlinedButton.icon(
                            onPressed: () => _chooseTime(arrival: false),
                            icon: const Icon(Icons.schedule_outlined),
                            label: Text('Departure · ${_checkOutTime.format(context)}'))),
                  ]),
                  const SizedBox(height: 8),
                  Row(children: [
                    const Text('Guests'),
                    const Spacer(),
                    IconButton(
                        onPressed: _guests > 1
                            ? () => setState(() {
                                  _guests--;
                                  _rooms = _loadRooms();
                                })
                            : null,
                        icon: const Icon(Icons.remove_circle_outline)),
                    Text('$_guests'),
                    IconButton(
                        onPressed: _guests < 12
                            ? () => setState(() {
                                  _guests++;
                                  _rooms = _loadRooms();
                                })
                            : null,
                        icon: const Icon(Icons.add_circle_outline)),
                    const SizedBox(width: 12),
                    const Text('Rooms'),
                    const SizedBox(width: 8),
                    DropdownButton<int>(
                        value: _roomCount,
                        items: [1, 2, 3, 4]
                            .map((v) =>
                                DropdownMenuItem(value: v, child: Text('$v')))
                            .toList(),
                        onChanged: (v) {
                          if (v != null)
                            setState(() {
                              _roomCount = v;
                              _rooms = _loadRooms();
                            });
                        })
                  ]),
                ])),
            const SizedBox(height: 16),
            FutureBuilder<List<Map<String, dynamic>>>(
                future: _rooms,
                builder: (context, snapshot) {
                  if (snapshot.connectionState == ConnectionState.waiting)
                    return const Center(
                        child: Padding(
                            padding: EdgeInsets.all(24),
                            child: CircularProgressIndicator()));
                  if (snapshot.hasError)
                    return VoltError(
                        message: '${snapshot.error}',
                        onRetry: () => setState(() => _rooms = _loadRooms()));
                  final rooms = snapshot.data ?? const <Map<String, dynamic>>[];
                  if (rooms.isEmpty)
                    return const VoltCard(
                        child: Text(
                            'No room inventory is available for those dates and guest count. Choose other dates or check again later.',
                            style: TextStyle(color: VoltColors.muted)));
                  return Column(
                      children: rooms
                          .map((room) => Padding(
                              padding: const EdgeInsets.only(bottom: 12),
                              child: VoltCard(
                                  child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                    Text('${room['room_name']}',
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w900,
                                            fontSize: 18)),
                                    if ('${room['description'] ?? ''}'
                                        .isNotEmpty)
                                      Padding(
                                          padding:
                                              const EdgeInsets.only(top: 5),
                                          child: Text('${room['description']}',
                                              style: const TextStyle(
                                                  color: VoltColors.muted))),
                                    const SizedBox(height: 8),
                                    Text(
                                        'Up to ${room['max_guests']} guests · ${room['available_nights'] ?? 'Availability varies'} nights available',
                                        style: const TextStyle(
                                            color: VoltColors.muted)),
                                    Text(
                                        'From ₹${room['nightly_rate_inr']} / night · Cancellation refund depends on timing'),
                                    const SizedBox(height: 4),
                                    Text(
                                        room['is_open_24_hours'] == true
                                            ? 'Available 24 hours'
                                            : 'Daily hours ${_displayTime(room['operating_start_time'])}–${_displayTime(room['operating_end_time'])}',
                                        style: const TextStyle(
                                            color: VoltColors.muted)),
                                    const SizedBox(height: 12),
                                    SizedBox(
                                        width: double.infinity,
                                        child: FilledButton(
                                            onPressed:
                                                _busy || _reservationId != null
                                                    ? null
                                                    : () => _reserve(room),
                                            child: _busy
                                                ? const SizedBox(
                                                    width: 18,
                                                    height: 18,
                                                    child:
                                                        CircularProgressIndicator(
                                                            strokeWidth: 2))
                                                : const Text('Review price'))),
                                  ]))))
                          .toList());
                }),
            if (_statusMessage != null) ...[
              const SizedBox(height: 10),
              VoltCard(
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                    Text(
                        _reservationId == null
                            ? 'Unable to start reservation'
                            : 'Reservation status',
                        style: const TextStyle(fontWeight: FontWeight.w800)),
                    const SizedBox(height: 6),
                    Text(_statusMessage!),
                    if (_reservationId != null)
                      TextButton.icon(
                          onPressed: _checkStatus,
                          icon: const Icon(Icons.refresh),
                          label: const Text('Check verified status'))
                  ])),
            ],
          ]));
}

class SlotSelectionScreen extends StatefulWidget {
  const SlotSelectionScreen(
      {super.key,
      required this.app,
      required this.vendor,
      required this.slots});
  final AppController app;
  final Pitstop vendor;
  final List<Map<String, dynamic>> slots;

  @override
  State<SlotSelectionScreen> createState() => _SlotSelectionScreenState();
}

class _SlotSelectionScreenState extends State<SlotSelectionScreen> {
  String? _lockingSlotId;
  late List<Map<String, dynamic>> _slots;
  StreamSubscription<void>? _pitstopChanges;
  Timer? _refreshDebounce;
  Timer? _fallbackRefresh;
  bool _refreshingAvailability = false;

  @override
  void initState() {
    super.initState();
    _slots = List<Map<String, dynamic>>.from(widget.slots);
    final repository = widget.app.driverRepository;
    _pitstopChanges = repository
        .watchPitstopChanges(widget.vendor.id)
        .listen((_) => _scheduleAvailabilityRefresh(), onError: (_) {});
    _fallbackRefresh = Timer.periodic(
      const Duration(seconds: 20),
      (_) => _refreshAvailability(),
    );
  }

  @override
  void dispose() {
    _refreshDebounce?.cancel();
    _fallbackRefresh?.cancel();
    _pitstopChanges?.cancel();
    super.dispose();
  }

  void _scheduleAvailabilityRefresh() {
    _refreshDebounce?.cancel();
    _refreshDebounce = Timer(
      const Duration(milliseconds: 180),
      _refreshAvailability,
    );
  }

  Future<void> _refreshAvailability() async {
    if (_refreshingAvailability) return;
    _refreshingAvailability = true;
    try {
      final slots = await widget.app.driverRepository.slots(widget.vendor.id);
      if (mounted) setState(() => _slots = slots);
    } catch (_) {
      // Keep the last server list visible; locking remains authoritative.
    } finally {
      _refreshingAvailability = false;
    }
  }

  Future<void> _select(Map<String, dynamic> slot) async {
    if (!widget.app.isSignedIn) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Sign in to reserve a slot.')));
      return;
    }
    setState(() => _lockingSlotId = '${slot['id']}');
    try {
      final lock = await widget.app.driverRepository.lockSlot('${slot['id']}');
      if (!mounted) return;
      final expiry =
          DateTime.tryParse('${lock['expires_at'] ?? ''}')?.toLocal();
      final seconds = int.tryParse('${lock['expires_in_seconds']}');
      final expiresAt =
          expiry ?? DateTime.now().add(Duration(seconds: seconds ?? 300));
      if (!expiresAt.isAfter(DateTime.now()))
        throw Exception(
            'The reservation window has expired. Please select this slot again.');
      Navigator.push(
          context,
          MaterialPageRoute(
              builder: (_) => BookingReviewScreen(
                  app: widget.app,
                  vendor: widget.vendor,
                  slot: slot,
                  lockToken: '${lock['lock_token']}',
                  expiresAt: expiresAt)));
    } catch (error) {
      if (mounted)
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Could not reserve slot: $error')));
    } finally {
      if (mounted) setState(() => _lockingSlotId = null);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Select a slot'), actions: [
          IconButton(
              tooltip: 'Refresh availability',
              onPressed: _refreshAvailability,
              icon: const Icon(Icons.refresh_rounded))
        ]),
        body: ListView(padding: const EdgeInsets.all(18), children: [
          Text(widget.vendor.name,
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 6),
          const Text(
              'Choose a date and time. The reservation countdown starts after you select a slot.',
              style: TextStyle(color: VoltColors.muted)),
          const SizedBox(height: 18),
          if (_slots.isEmpty)
            const VoltCard(
                child: Text('No available times. Try again later.',
                    style: TextStyle(color: VoltColors.muted))),
          ..._slots.map((slot) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _SlotTile(
                  slot: slot,
                  busy: _lockingSlotId == '${slot['id']}',
                  enabled: _lockingSlotId == null,
                  onSelect: () => _select(slot)))),
        ]),
      );
}

class _SlotTile extends StatelessWidget {
  const _SlotTile(
      {required this.slot,
      required this.onSelect,
      this.busy = false,
      this.enabled = true,
      this.showSelect = true});
  final Map<String, dynamic> slot;
  final VoidCallback onSelect;
  final bool busy;
  final bool enabled;
  final bool showSelect;
  @override
  Widget build(BuildContext context) {
    final start = DateTime.tryParse('${slot['slot_start_time']}')?.toLocal();
    final end = DateTime.tryParse('${slot['slot_end_time']}')?.toLocal();
    final time = '${_time(start)} – ${_time(end)}';
    return VoltCard(
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 10),
        child: Row(children: [
          const Icon(Icons.schedule, color: VoltColors.cyan),
          const SizedBox(width: 10),
          Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                Text(time, style: const TextStyle(fontWeight: FontWeight.w800)),
                Text(
                    '${start == null ? 'Date to be confirmed' : '${start.day}/${start.month}/${start.year}'} • ${slot['capacity'] ?? 1} capacity • ₹${slot['price_inr'] ?? '—'}',
                    style:
                        const TextStyle(color: VoltColors.muted, fontSize: 12))
              ])),
          if (showSelect)
            FilledButton(
                onPressed: enabled ? onSelect : null,
                child: busy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Select'))
        ]));
  }
}

String _hotelDate(dynamic value) {
  final parsed = DateTime.tryParse('${value ?? ''}');
  if (parsed == null) return 'Date pending';
  return '${parsed.day}/${parsed.month}/${parsed.year}';
}

String _hotelTime(dynamic value) {
  final raw = '${value ?? ''}';
  final parts = raw.split(':');
  if (parts.length < 2) return 'Time not set';
  final hour = int.tryParse(parts[0]);
  final minute = int.tryParse(parts[1]);
  if (hour == null || minute == null) return 'Time not set';
  final local = TimeOfDay(hour: hour, minute: minute);
  final period = local.period == DayPeriod.am ? 'AM' : 'PM';
  final displayHour = local.hourOfPeriod == 0 ? 12 : local.hourOfPeriod;
  return '${displayHour.toString().padLeft(2, '0')}:${minute.toString().padLeft(2, '0')} $period';
}

String _time(DateTime? value) {
  if (value == null) return 'Time TBA';
  final hour = value.hour % 12 == 0 ? 12 : value.hour % 12;
  return '${hour.toString().padLeft(2, '0')}:${value.minute.toString().padLeft(2, '0')} ${value.hour < 12 ? 'AM' : 'PM'}';
}

class BookingReviewScreen extends StatefulWidget {
  const BookingReviewScreen(
      {super.key,
      required this.app,
      required this.vendor,
      required this.slot,
      required this.lockToken,
      required this.expiresAt});
  final AppController app;
  final Pitstop vendor;
  final Map<String, dynamic> slot;
  final String lockToken;
  final DateTime expiresAt;

  @override
  State<BookingReviewScreen> createState() => _BookingReviewScreenState();
}

class _BookingReviewScreenState extends State<BookingReviewScreen> {
  late Timer _timer;
  bool _expired = false;

  @override
  void initState() {
    super.initState();
    _tick();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _tick());
  }

  void _tick() {
    if (!mounted) return;
    final expired = !widget.expiresAt.isAfter(DateTime.now());
    if (expired != _expired) setState(() => _expired = expired);
  }

  @override
  void dispose() {
    _timer.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final start =
        DateTime.tryParse('${widget.slot['slot_start_time']}')?.toLocal();
    final end = DateTime.tryParse('${widget.slot['slot_end_time']}')?.toLocal();
    final price = double.tryParse('${widget.slot['price_inr']}') ?? 0;
    return Scaffold(
        appBar: AppBar(title: const Text('Booking review')),
        body: ListView(padding: const EdgeInsets.all(18), children: [
          VoltCard(
              color: VoltColors.elevated,
              child: Row(children: [
                const Icon(Icons.timer_outlined, color: VoltColors.forest),
                const SizedBox(width: 10),
                const Expanded(
                    child: Text('Slot held for payment for',
                        style: TextStyle(
                            color: VoltColors.forest,
                            fontWeight: FontWeight.w600))),
                _Countdown(expiresAt: widget.expiresAt)
              ])),
          const SizedBox(height: 16),
          const Text('Review your stop',
              style: TextStyle(fontWeight: FontWeight.w900, fontSize: 22)),
          const SizedBox(height: 13),
          VoltCard(
              child: Column(children: [
            _ReviewRow(label: 'Vendor', value: widget.vendor.name),
            _ReviewRow(
                label: 'Service',
                value: widget.vendor.services.isEmpty
                    ? 'Charging reservation'
                    : widget.vendor.services
                        .map((s) => _serviceName('${s['service_type']}'))
                        .join(', ')),
            _ReviewRow(
                label: 'Date',
                value: start == null
                    ? 'Date to be confirmed'
                    : '${start.day}/${start.month}/${start.year}'),
            _ReviewRow(label: 'Time', value: '${_time(start)} – ${_time(end)}'),
            const Divider(),
            _ReviewRow(
                label: 'Total payable',
                value: '₹${price.toStringAsFixed(0)}',
                strong: true)
          ])),
          const SizedBox(height: 18),
          const Text(
              'Taxes and fees are included only when listed by the service provider.',
              style: TextStyle(color: VoltColors.muted, fontSize: 12)),
          const SizedBox(height: 10),
          const VoltCard(
              child: Text(
                  'Cancellation refund depends on when you cancel: 48+ hours before service 100%, 24–48 hours 90%, under 24 hours 50%, and after service starts no refund. No extra gateway fee is deducted.')),
          const SizedBox(height: 18),
          SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                  onPressed: _expired
                      ? null
                      : () => Navigator.push(
                          context,
                          MaterialPageRoute(
                              builder: (_) => PaymentScreen(
                                  app: widget.app,
                                  vendor: widget.vendor,
                                  slot: widget.slot,
                                  lockToken: widget.lockToken))),
                  icon: const Icon(Icons.lock_outline),
                  label: Text(_expired
                      ? 'Reservation expired'
                      : 'Proceed to Payment'))),
        ]));
  }
}

class _ReviewRow extends StatelessWidget {
  const _ReviewRow(
      {required this.label, required this.value, this.strong = false});
  final String label;
  final String value;
  final bool strong;
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label,
            style: const TextStyle(color: VoltColors.muted, fontSize: 12)),
        const SizedBox(height: 2),
        SelectableText(value,
            style: TextStyle(
                fontWeight: strong ? FontWeight.w900 : FontWeight.w700,
                color: strong ? VoltColors.green : VoltColors.text,
                fontSize: strong ? 18 : 14))
      ]));
}

class _Countdown extends StatefulWidget {
  const _Countdown({required this.expiresAt});
  final DateTime expiresAt;
  @override
  State<_Countdown> createState() => _CountdownState();
}

class _CountdownState extends State<_Countdown> {
  late Timer _timer;
  int _seconds = 0;
  @override
  void initState() {
    super.initState();
    _tick();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _tick());
  }

  void _tick() {
    if (mounted)
      setState(() => _seconds = widget.expiresAt
          .difference(DateTime.now())
          .inSeconds
          .clamp(0, 9999)
          .toInt());
  }

  @override
  void dispose() {
    _timer.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Text(
      '${(_seconds ~/ 60).toString().padLeft(2, '0')}:${(_seconds % 60).toString().padLeft(2, '0')}',
      style:
          const TextStyle(color: VoltColors.cyan, fontWeight: FontWeight.w900));
}

class PaymentScreen extends StatefulWidget {
  const PaymentScreen(
      {super.key,
      required this.app,
      required this.vendor,
      required this.slot,
      required this.lockToken});
  final AppController app;
  final Pitstop vendor;
  final Map<String, dynamic> slot;
  final String lockToken;
  @override
  State<PaymentScreen> createState() => _PaymentScreenState();
}

class _PaymentScreenState extends State<PaymentScreen> {
  Razorpay? _razorpay;
  Booking? _booking;
  String _state = 'ready';
  String? _message;
  bool _creating = false;
  bool _awaitingServerConfirmation = false;
  bool _checkingBackend = false;
  bool _verifyingCheckout = false;
  StreamSubscription<void>? _bookingChanges;
  Timer? _statusFallback;

  @override
  void initState() {
    super.initState();
    _razorpay = Razorpay();
    _razorpay!.on(Razorpay.EVENT_PAYMENT_SUCCESS, _onSuccess);
    _razorpay!.on(Razorpay.EVENT_PAYMENT_ERROR, _onPaymentError);
    _razorpay!.on(Razorpay.EVENT_EXTERNAL_WALLET, (_) => _checkBackend());
  }

  @override
  void dispose() {
    _statusFallback?.cancel();
    _bookingChanges?.cancel();
    _razorpay?.clear();
    super.dispose();
  }

  Future<void> _begin() async {
    setState(() {
      _creating = true;
      _state = 'ready';
      _message = null;
    });
    try {
      final booking = await widget.app.driverRepository
          .createBooking('${widget.slot['id']}', widget.lockToken);
      if (!mounted) return;
      _booking = booking;
      _bookingChanges =
          widget.app.driverRepository.watchBooking(booking.id).listen((_) {
        if (_awaitingServerConfirmation) _checkBackend();
      }, onError: (_) {});
      if (booking.keyId == null ||
          booking.orderId == null ||
          booking.amountPaise == null)
        throw Exception('Payment order is missing trusted gateway details.');
      setState(() {
        _creating = false;
        _state = 'paying';
      });
      _razorpay!.open({
        'key': booking.keyId,
        'order_id': booking.orderId,
        'amount': booking.amountPaise ?? 0,
        'currency': 'INR',
        'name': 'VoltStop',
        'description': 'Charging reservation at ${widget.vendor.name}',
        'prefill': {'contact': widget.app.profile?.phone ?? ''}
      });
    } catch (error) {
      if (mounted)
        setState(() {
          _creating = false;
          _state = 'failed';
          _message = '$error';
        });
    }
  }

  Future<void> _onSuccess(PaymentSuccessResponse response) async {
    _awaitingServerConfirmation = true;
    _verifyingCheckout = true;
    final booking = _booking;
    final paymentId = response.paymentId;
    final signature = response.signature;
    final orderId = response.orderId ?? booking?.orderId;
    if (booking != null &&
        orderId != null &&
        paymentId != null &&
        signature != null) {
      try {
        await widget.app.driverRepository.verifyRazorpayCheckout(
          orderId: orderId,
          paymentId: paymentId,
          signature: signature,
        );
      } catch (_) {
        // Keep checking the API; do not treat the native SDK callback as payment proof.
      }
    }
    _verifyingCheckout = false;
    await _checkBackend();
  }

  void _onPaymentError(PaymentFailureResponse _) {
    _awaitingServerConfirmation = true;
    _checkBackend();
  }

  Future<void> _checkBackend() async {
    final booking = _booking;
    if (booking == null || _checkingBackend || _verifyingCheckout) return;
    _awaitingServerConfirmation = true;
    _checkingBackend = true;
    if (mounted)
      setState(() {
        _state = 'processing';
        _message = 'Checking the payment result with VoltStop’s secure server…';
      });
    try {
      final updated = await widget.app.driverRepository.booking(booking.id);
      if (!mounted) return;
      if (updated.status == 'confirmed') {
        _stopStatusMonitoring();
        Navigator.of(context).pushAndRemoveUntil(
            MaterialPageRoute(
                builder: (_) => BookingSuccessScreen(
                    app: widget.app, booking: updated, vendor: widget.vendor)),
            (route) => route.isFirst);
        return;
      }
      if (updated.status == 'failed' ||
          updated.status == 'cancelled' ||
          updated.status == 'expired' ||
          updated.paymentStatus == 'failed') {
        _stopStatusMonitoring();
        setState(() {
          _state = 'failed';
          _message =
              'The secure server reports that this payment did not complete.';
        });
        return;
      }
      setState(() {
        _state = 'processing';
        _message =
            'Confirmation is pending. Live status updates are active; do not pay again while the server verifies this order.';
      });
      _startStatusFallback();
    } catch (_) {
      if (mounted) {
        setState(() {
          _state = 'processing';
          _message =
              'We could not check the server just now. Live updates and automatic retries are active; do not pay again.';
        });
        _startStatusFallback();
      }
    } finally {
      _checkingBackend = false;
    }
  }

  void _startStatusFallback() {
    _statusFallback ??= Timer.periodic(
      const Duration(seconds: 15),
      (_) => _checkBackend(),
    );
  }

  void _stopStatusMonitoring() {
    _statusFallback?.cancel();
    _statusFallback = null;
    _bookingChanges?.cancel();
    _bookingChanges = null;
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: const Text('Secure payment')),
      body: Center(
          child: Padding(
              padding: const EdgeInsets.all(22),
              child: _state == 'processing'
                  ? Column(mainAxisSize: MainAxisSize.min, children: [
                      const CircularProgressIndicator(color: VoltColors.green),
                      const SizedBox(height: 18),
                      Text('Payment Processing',
                          style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: 8),
                      Text(_message ?? 'Waiting for confirmation…',
                          textAlign: TextAlign.center,
                          style: const TextStyle(color: VoltColors.muted)),
                      if (_booking != null)
                        TextButton(
                            onPressed: _checkBackend,
                            child: const Text('Check status again'))
                    ])
                  : _state == 'failed'
                      ? Column(mainAxisSize: MainAxisSize.min, children: [
                          const Icon(Icons.error_outline,
                              color: VoltColors.red, size: 46),
                          const SizedBox(height: 14),
                          Text('Payment Failed',
                              style: Theme.of(context).textTheme.titleLarge),
                          const SizedBox(height: 8),
                          Text(_message ?? 'The payment could not be started.',
                              textAlign: TextAlign.center),
                          const SizedBox(height: 16),
                          FilledButton(
                              onPressed: () => Navigator.pop(context),
                              child: const Text('Back to booking'))
                        ])
                      : Column(mainAxisSize: MainAxisSize.min, children: [
                          const Icon(Icons.lock,
                              color: VoltColors.cyan, size: 46),
                          const SizedBox(height: 14),
                          Text('₹${widget.slot['price_inr'] ?? '—'}',
                              style:
                                  Theme.of(context).textTheme.headlineMedium),
                          const SizedBox(height: 8),
                          const Text(
                              'Payment status will be confirmed by VoltStop after the gateway webhook is verified.',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: VoltColors.muted)),
                          if (_message != null)
                            Padding(
                                padding: const EdgeInsets.only(top: 12),
                                child: Text(_message!,
                                    style: const TextStyle(
                                        color: VoltColors.red))),
                          const SizedBox(height: 20),
                          SizedBox(
                              width: double.infinity,
                              child: FilledButton(
                                  onPressed: _creating || _state == 'paying'
                                      ? null
                                      : _begin,
                                  child: _creating
                                      ? const CircularProgressIndicator()
                                      : const Text(
                                          'Pay securely with Razorpay')))
                        ]))));
}

class BookingSuccessScreen extends StatelessWidget {
  const BookingSuccessScreen(
      {super.key,
      required this.app,
      required this.booking,
      required this.vendor});
  final AppController app;
  final Booking booking;
  final Pitstop vendor;
  @override
  Widget build(BuildContext context) => Scaffold(
      body: SafeArea(
          child: Center(
              child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    const Icon(Icons.check_circle,
                        color: VoltColors.green, size: 76),
                    const SizedBox(height: 18),
                    Text('Booking Confirmed',
                        style: Theme.of(context).textTheme.headlineMedium),
                    const SizedBox(height: 8),
                    Text('${vendor.name}\nBooking ${booking.id}',
                        textAlign: TextAlign.center,
                        style: const TextStyle(color: VoltColors.muted)),
                    const SizedBox(height: 22),
                    SizedBox(
                        width: double.infinity,
                        child: FilledButton(
                            onPressed: () => Navigator.of(context)
                                .pushAndRemoveUntil(
                                    MaterialPageRoute(
                                        builder: (_) => DriverShell(
                                            app: app, initialIndex: 2)),
                                    (_) => false),
                            child: const Text('Go to My Bookings')))
                  ])))));
}

class _DeparturePicker extends StatelessWidget {
  const _DeparturePicker({required this.value, required this.onChanged});
  final DateTime value;
  final ValueChanged<DateTime> onChanged;

  Future<void> _chooseDate(BuildContext context) async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: value.isBefore(DateUtils.dateOnly(now))
          ? DateUtils.dateOnly(now)
          : value,
      firstDate: DateUtils.dateOnly(now),
      lastDate: DateUtils.dateOnly(now).add(const Duration(days: 365)),
    );
    if (picked == null || !context.mounted) return;
    onChanged(DateTime(
        picked.year, picked.month, picked.day, value.hour, value.minute));
  }

  Future<void> _chooseTime(BuildContext context) async {
    final picked = await showTimePicker(
        context: context, initialTime: TimeOfDay.fromDateTime(value));
    if (picked == null || !context.mounted) return;
    final candidate = DateTime(
        value.year, value.month, value.day, picked.hour, picked.minute);
    if (candidate
        .isBefore(DateTime.now().subtract(const Duration(minutes: 5)))) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Choose a departure time that is now or later.')));
      return;
    }
    onChanged(candidate);
  }

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.fromLTRB(13, 11, 13, 12),
        decoration: BoxDecoration(
          color: VoltColors.elevated.withValues(alpha: .72),
          borderRadius: BorderRadius.circular(VoltRadii.control),
          border: Border.all(color: VoltColors.border.withValues(alpha: .8)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              const VoltIconBadge(
                  icon: Icons.event_available_outlined, size: 34),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Planned departure',
                        style: Theme.of(context).textTheme.titleSmall),
                    Text('Set your expected start time',
                        style: Theme.of(context).textTheme.bodySmall),
                  ],
                ),
              ),
            ]),
            const SizedBox(height: 10),
            Row(children: [
              Expanded(
                  child: _departureButton(
                context,
                icon: Icons.calendar_today_outlined,
                onPressed: () => _chooseDate(context),
                label:
                    MaterialLocalizations.of(context).formatMediumDate(value),
              )),
              const SizedBox(width: 8),
              Expanded(
                  child: _departureButton(
                context,
                icon: Icons.schedule_rounded,
                onPressed: () => _chooseTime(context),
                label: MaterialLocalizations.of(context)
                    .formatTimeOfDay(TimeOfDay.fromDateTime(value)),
              )),
            ]),
          ],
        ),
      );

  Widget _departureButton(BuildContext context,
          {required IconData icon,
          required VoidCallback onPressed,
          required String label}) =>
      OutlinedButton.icon(
        onPressed: onPressed,
        icon: Icon(icon, size: 16),
        label: Text(label, maxLines: 1, overflow: TextOverflow.ellipsis),
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(0, 44),
          padding: const EdgeInsets.symmetric(horizontal: 8),
          backgroundColor: VoltColors.surface,
          textStyle: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
        ),
      );
}

class RoutePlannerScreen extends StatefulWidget {
  const RoutePlannerScreen(
      {super.key,
      required this.app,
      required this.origin,
      required this.destination,
      required this.soc,
      required this.departureAt});
  final AppController app;
  final String origin;
  final String destination;
  final double? soc;
  final DateTime departureAt;
  @override
  State<RoutePlannerScreen> createState() => _RoutePlannerScreenState();
}

class _RoutePlannerScreenState extends State<RoutePlannerScreen> {
  late Future<Map<String, dynamic>> _route;
  double? _soc;
  bool _chargeSaved = false;
  late DateTime _departureAt;
  bool _savingCharge = false;
  String? _chargeError;
  StreamSubscription<void>? _catalogChanges;
  Timer? _refreshDebounce;
  @override
  void initState() {
    super.initState();
    _soc = widget.soc ??
        widget.app.activeVehicle?.currentSoc ??
        widget.app.profile?.currentSoc;
    _departureAt = widget.departureAt;
    _chargeSaved = (widget.app.activeVehicle?.currentSoc ??
                widget.app.profile?.currentSoc) !=
            null &&
        (widget.app.activeVehicle?.currentSoc ??
                widget.app.profile?.currentSoc) ==
            _soc;
    _route = _plan();
    _catalogChanges = widget.app.driverRepository
        .watchPitstopDirectoryChanges()
        .listen((_) => _scheduleRefresh(), onError: (_) {});
  }

  @override
  void dispose() {
    _refreshDebounce?.cancel();
    _catalogChanges?.cancel();
    super.dispose();
  }

  void _scheduleRefresh() {
    _refreshDebounce?.cancel();
    _refreshDebounce = Timer(const Duration(milliseconds: 250), () {
      if (mounted) {
        setState(() {
          _route = _plan(persist: false);
        });
      }
    });
  }

  Future<Map<String, dynamic>> _plan({bool persist = true}) {
    final battery =
        widget.app.activeVehicle?.batteryKwh ?? widget.app.profile?.batteryKwh;
    final efficiency = widget.app.activeVehicle?.efficiencyKmPerKwh ??
        widget.app.profile?.efficiencyKmPerKwh;
    final stateOfCharge = _soc;
    if (battery == null || efficiency == null) {
      return Future.error(
          StateError('Complete your EV profile to plan this route.'));
    }
    if (stateOfCharge == null) {
      return Future.error(
          StateError('Set your current battery charge to plan this route.'));
    }
    return widget.app.driverRepository.planRoute(
      origin: widget.origin,
      destination: widget.destination,
      batteryKwh: battery,
      stateOfCharge: stateOfCharge,
      efficiency: efficiency,
      persist: persist,
      departureAt: _departureAt,
    );
  }

  Future<void> _saveChargeAndPlan() async {
    final charge = _soc;
    if (charge == null) return;
    setState(() {
      _savingCharge = true;
      _chargeError = null;
    });
    try {
      final vehicle = widget.app.activeVehicle;
      if (vehicle != null) {
        await widget.app.driverRepository
            .updateVehicle(vehicle.id, {'current_soc': charge});
        await widget.app.refreshVehicles();
      } else {
        final profile = widget.app.profile ?? const DriverProfile();
        await widget.app.saveProfile(profile.copyWith(currentSoc: charge));
      }
      if (mounted) {
        setState(() {
          _chargeSaved = true;
          _route = _plan();
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() => _chargeError =
            'Could not save your charge. Check your connection and retry.');
      }
    } finally {
      if (mounted) setState(() => _savingCharge = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: const Text('Route planner'), actions: [
        IconButton(
            tooltip: 'Refresh route estimate',
            onPressed: _scheduleRefresh,
            icon: const Icon(Icons.refresh_rounded))
      ]),
      body: FutureBuilder<Map<String, dynamic>>(
          future: _route,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting &&
                _chargeSaved)
              return const VoltLoading(label: 'Calculating route and energy…');
            if (!widget.app.profileComplete)
              return Center(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: VoltCard(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Text(
                          'Add your EV model, battery capacity, and efficiency before planning a route.',
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 16),
                        FilledButton(
                          onPressed: () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) =>
                                  ProfileSetupScreen(app: widget.app),
                            ),
                          ),
                          child: const Text('Complete EV profile'),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            if (!_chargeSaved)
              return Center(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: VoltCard(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          'Set your current battery charge',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        const SizedBox(height: 6),
                        const Text(
                          'Choose the charge shown by your vehicle. VoltStop will save it to your profile and use it for this estimate.',
                          style: TextStyle(color: VoltColors.muted),
                        ),
                        const SizedBox(height: 16),
                        Text(
                          _soc == null
                              ? 'Choose a percentage'
                              : '${_soc!.round()}%',
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.titleLarge,
                        ),
                        Slider(
                          value: _soc ?? 50,
                          min: 0,
                          max: 100,
                          divisions: 20,
                          label: _soc == null ? null : '${_soc!.round()}%',
                          onChanged: (value) => setState(() {
                            _soc = value;
                            _chargeError = null;
                          }),
                        ),
                        if (_chargeError != null)
                          Text(
                            _chargeError!,
                            style: const TextStyle(color: VoltColors.warning),
                          ),
                        const SizedBox(height: 8),
                        FilledButton(
                          onPressed: _soc == null || _savingCharge
                              ? null
                              : _saveChargeAndPlan,
                          child: Text(
                            _savingCharge
                                ? 'Saving…'
                                : 'Save charge & calculate route',
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            if (snapshot.hasError)
              return Center(
                  child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: VoltError(
                          message: snapshot.error is ApiException
                              ? (snapshot.error as ApiException).message
                              : snapshot.error is StateError
                                  ? (snapshot.error as StateError).message
                                  : 'Route estimates are unavailable. Check your connection and try again.',
                          onRetry: () {
                            setState(() {
                              _route = _plan(persist: false);
                            });
                          })));
            final data = snapshot.data!;
            final consumption =
                double.tryParse('${data['estimated_consumption_kwh']}') ?? 0;
            final distance = double.tryParse('${data['distance_km']}') ?? 0;
            final remaining =
                double.tryParse('${data['estimated_remaining_soc']}') ?? 0;
            final vehicle = widget.app.activeVehicle;
            final batteryKwh =
                vehicle?.batteryKwh ?? widget.app.profile?.batteryKwh ?? 0;
            final efficiency = vehicle?.efficiencyKmPerKwh ??
                widget.app.profile?.efficiencyKmPerKwh ??
                0;
            final vehicleName = vehicle?.displayName ??
                widget.app.profile?.carModel ??
                'EV profile';
            final routeStops = _routePitstops(data);
            return ListView(padding: const EdgeInsets.all(18), children: [
              _DeparturePicker(
                value: _departureAt,
                onChanged: (value) => setState(() {
                  _departureAt = value;
                  _route = _plan();
                }),
              ),
              const SizedBox(height: 12),
              _RoutePreview(
                  data: data,
                  origin: widget.origin,
                  destination: widget.destination),
              const SizedBox(height: 16),
              VoltCard(
                  child: Column(children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text('Trip details',
                      style: Theme.of(context).textTheme.titleMedium),
                ),
                const SizedBox(height: 4),
                _ReviewRow(
                    label: 'Travel date',
                    value: MaterialLocalizations.of(context)
                        .formatMediumDate(_departureAt)),
                _ReviewRow(
                    label: 'Departure time',
                    value: MaterialLocalizations.of(context)
                        .formatTimeOfDay(TimeOfDay.fromDateTime(_departureAt))),
                _ReviewRow(label: 'Vehicle', value: vehicleName),
                _ReviewRow(
                    label: 'Battery capacity',
                    value: '${batteryKwh.toStringAsFixed(0)} kWh'),
                _ReviewRow(
                    label: 'Starting charge', value: '${(_soc ?? 0).round()}%'),
                _ReviewRow(
                    label: 'Efficiency',
                    value: '${efficiency.toStringAsFixed(1)} km/kWh'),
              ])),
              const SizedBox(height: 12),
              VoltCard(
                  child: Column(children: [
                _ReviewRow(
                    label: 'Route',
                    value: '${widget.origin} → ${widget.destination}'),
                _ReviewRow(
                    label: 'Distance',
                    value: '${distance.toStringAsFixed(0)} km'),
                if (data['estimated_duration_seconds'] is num)
                  _ReviewRow(
                    label: 'Estimated drive time',
                    value: _formatRouteDuration(
                      (data['estimated_duration_seconds'] as num).round(),
                    ),
                  ),
                _ReviewRow(
                    label: 'Approx. energy',
                    value: '${consumption.toStringAsFixed(1)} kWh'),
                _ReviewRow(
                    label: 'Estimated arrival battery',
                    value: '${remaining.clamp(0, 100).toStringAsFixed(0)}%')
              ])),
              const SizedBox(height: 10),
              const Text(
                  'These values are estimates based on your default efficiency. Actual consumption varies with speed, weather, terrain, traffic and vehicle load.',
                  style: TextStyle(color: VoltColors.warning, fontSize: 12)),
              const SizedBox(height: 18),
              Text('Route stops (${routeStops.length})',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              const Text(
                'Stations are partner listings. Live charger plug status requires a provider connection.',
                style: TextStyle(color: VoltColors.muted, fontSize: 12),
              ),
              if (routeStops.isEmpty)
                const Padding(
                  padding: EdgeInsets.only(top: 10),
                  child: VoltCard(
                    child: Text(
                      'No partner stops are listed within 15 km of this route yet. Search nearby towns in Explore.',
                      style: TextStyle(color: VoltColors.muted),
                    ),
                  ),
                )
              else
                ...routeStops.map((vendor) {
                  return Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: ListTile(
                      tileColor: VoltColors.surface,
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14)),
                      leading: Icon(_pitstopIcon(vendor),
                          color: _pitstopColor(vendor)),
                      title: Text(vendor.name),
                      subtitle: Text(
                          '${_serviceName(vendor.type)} · ${vendor.distanceKm.toStringAsFixed(1)} km from route'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => PitstopDetailsScreen(
                              app: widget.app, vendorId: vendor.id),
                        ),
                      ),
                    ),
                  );
                }),
            ]);
          }));
}

class BookingsScreen extends StatefulWidget {
  const BookingsScreen({super.key, required this.app});
  final AppController app;
  @override
  State<BookingsScreen> createState() => _BookingsScreenState();
}

class _BookingsScreenState extends State<BookingsScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;
  late Future<List<Booking>> _bookings;
  late Future<List<Map<String, dynamic>>> _hotelReservations;
  StreamSubscription<void>? _bookingChanges;
  Timer? _refreshDebounce;
  Timer? _fallbackRefresh;
  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 4, vsync: this);
    final repository = widget.app.driverRepository;
    _bookings = repository.bookings();
    _hotelReservations = repository.hotelReservations();
    _bookingChanges = repository.watchBookings().listen(
          (_) => _scheduleRefresh(),
          onError: (_) {},
        );
    _fallbackRefresh = Timer.periodic(
      const Duration(seconds: 30),
      (_) => _scheduleRefresh(),
    );
  }

  void _scheduleRefresh() {
    _refreshDebounce?.cancel();
    _refreshDebounce = Timer(const Duration(milliseconds: 180), () {
      if (mounted) {
        setState(() {
          _bookings = widget.app.driverRepository.bookings();
          _hotelReservations = widget.app.driverRepository.hotelReservations();
        });
      }
    });
  }

  @override
  void dispose() {
    _refreshDebounce?.cancel();
    _fallbackRefresh?.cancel();
    _bookingChanges?.cancel();
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Column(children: [
        Padding(
            padding: const EdgeInsets.fromLTRB(18, 16, 18, 8),
            child: Row(children: [
              const Icon(Icons.bolt, color: VoltColors.green),
              const SizedBox(width: 8),
              Text('My Trips',
                  style: Theme.of(context)
                      .textTheme
                      .headlineSmall
                      ?.copyWith(fontWeight: FontWeight.w900)),
              const Spacer(),
              IconButton(
                  tooltip: 'Refresh trips',
                  onPressed: _scheduleRefresh,
                  icon: const Icon(Icons.refresh))
            ])),
        TabBar(controller: _tabs, tabs: const [
          Tab(text: 'Upcoming'),
          Tab(text: 'Completed'),
          Tab(text: 'Cancelled'),
          Tab(text: 'Hotel stays')
        ]),
        Expanded(
            child: FutureBuilder<List<Booking>>(
                future: _bookings,
                builder: (context, snapshot) {
                  if (snapshot.connectionState == ConnectionState.waiting)
                    return const VoltLoading(label: 'Loading your trips…');
                  if (snapshot.hasError)
                    return Padding(
                        padding: const EdgeInsets.all(18),
                        child: VoltError(
                            message: '${snapshot.error}',
                            onRetry: _scheduleRefresh));
                  final bookings = snapshot.data!;
                  return TabBarView(controller: _tabs, children: [
                    _bookingList(
                        bookings
                            .where((b) =>
                                b.status == 'pending' ||
                                b.status == 'confirmed')
                            .toList(),
                        'No upcoming bookings. Reserve a stop along your route.'),
                    _bookingList(
                        bookings.where((b) => b.status == 'completed').toList(),
                        'Completed trips will appear here.'),
                    _bookingList(
                        bookings
                            .where((b) =>
                                b.status == 'cancelled' ||
                                b.status == 'failed' ||
                                b.status == 'expired')
                            .toList(),
                        'No cancelled bookings.'),
                    _hotelReservationList(),
                  ]);
                })),
      ]);

  Widget _hotelReservationList() => FutureBuilder<List<Map<String, dynamic>>>(
      future: _hotelReservations,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const VoltLoading(label: 'Loading hotel reservations…');
        }
        if (snapshot.hasError) {
          return Padding(
              padding: const EdgeInsets.all(18),
              child: VoltError(
                  message: '${snapshot.error}',
                  onRetry: () => setState(() => _hotelReservations =
                      widget.app.driverRepository.hotelReservations())));
        }
        final reservations = snapshot.data ?? const <Map<String, dynamic>>[];
        if (reservations.isEmpty) {
          return const Center(
              child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Text(
                      'Hotel reservations will appear here with their verified payment status.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: VoltColors.muted))));
        }
        return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: reservations.length,
            itemBuilder: (context, index) {
              final item = reservations[index];
              final status = '${item['status'] ?? 'unknown'}';
              final canCancel =
                  status == 'payment_pending' || status == 'confirmed';
              return Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: VoltCard(
                      child: ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: const CircleAvatar(
                              backgroundColor: VoltColors.elevated,
                              child:
                                  Icon(Icons.hotel, color: VoltColors.green)),
                          title: Text(
                              '${item['vendor_name'] ?? 'Hotel'} · ${item['room_name'] ?? 'Room'}',
                              style:
                                  const TextStyle(fontWeight: FontWeight.w800)),
                          subtitle: Text(
                              '${_hotelDate(item['check_in'])} ${_hotelTime(item['check_in_time'])} – ${_hotelDate(item['check_out'])} ${_hotelTime(item['check_out_time'])} · ${item['guests']} guests\n₹${item['amount_inr']} · $status · payment ${item['payment_status'] ?? 'pending'}${item['refund_amount_inr'] != null ? '\nRefund ₹${item['refund_amount_inr']} · retained ₹${item['cancellation_fee_inr'] ?? 0}' : ''}',
                              maxLines: 3),
                          trailing: canCancel
                              ? IconButton(
                                  tooltip: 'Cancel reservation',
                                  onPressed: () =>
                                      _cancelHotelReservation(item),
                                  icon: const Icon(Icons.cancel_outlined,
                                      color: VoltColors.red))
                              : const Icon(Icons.chevron_right),
                          onTap: () => _showHotelReservation(item))));
            });
      });

  Future<void> _showHotelReservation(Map<String, dynamic> item) async {
    await showModalBottomSheet<void>(
        context: context,
        showDragHandle: true,
        builder: (context) => Padding(
            padding: const EdgeInsets.fromLTRB(22, 10, 22, 32),
            child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                      '${item['vendor_name'] ?? 'Hotel'} · ${item['room_name'] ?? 'Room'}',
                      style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 8),
                  Text(
                      '${_hotelDate(item['check_in'])} ${_hotelTime(item['check_in_time'])} arrival\n${_hotelDate(item['check_out'])} ${_hotelTime(item['check_out_time'])} departure'),
                  Text('${item['rooms']} room(s) · ${item['guests']} guest(s)'),
                  Text('₹${item['amount_inr']} · ${item['status']}'),
                  Text('Payment: ${item['payment_status'] ?? 'pending'}'),
                  if (item['refund_amount_inr'] != null)
                    Text('Refund ₹${item['refund_amount_inr']} · retained ₹${item['cancellation_fee_inr'] ?? 0}'),
                  if (item['vendor_lat'] is num && item['vendor_lng'] is num)
                    SizedBox(
                        width: double.infinity,
                        child: OutlinedButton.icon(
                            onPressed: () => Navigator.push(
                                context,
                                MaterialPageRoute(
                                    builder: (_) => DestinationMapScreen(
                                        latitude: (item['vendor_lat'] as num)
                                            .toDouble(),
                                        longitude: (item['vendor_lng'] as num)
                                            .toDouble(),
                                        title: '${item['vendor_name'] ?? 'Hotel'}',
                                        address: item['vendor_address']?.toString(),
                                        serviceType: 'hotel'))),
                            icon: const Icon(Icons.directions),
                            label: const Text('Directions to hotel'))),
                  if (item['status'] == 'refund_pending')
                    const Text(
                        'Cancellation is recorded. Refund awaits finance review.',
                        style: TextStyle(color: VoltColors.muted)),
                  if (item['status'] == 'refund_failed')
                    const Text(
                        'Cancellation is recorded, but the refund provider reported a failure. Contact VoltStop support.',
                        style: TextStyle(color: VoltColors.red)),
                ])));
  }

  Future<void> _cancelHotelReservation(Map<String, dynamic> item) async {
    Map<String, dynamic> quote;
    try {
      quote = await widget.app.driverRepository
          .hotelCancellationQuote('${item['id']}');
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Could not check refund estimate: $error')));
      }
      return;
    }
    final refund = quote['customer_refund_inr'] ?? 0;
    final retained = quote['retained_amount_inr'] ?? 0;
    final confirm = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
              title: const Text('Cancel hotel reservation?'),
              content: Text(
                  'Estimated refund: ₹$refund\nRetained amount: ₹$retained\n\nNo extra gateway fee is deducted. The final amount is checked by the server; eligible refunds are reviewed by finance.'),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(context, false),
                    child: const Text('Keep stay')),
                FilledButton(
                    onPressed: () => Navigator.pop(context, true),
                    child: const Text('Request cancellation'))
              ],
            ));
    if (confirm != true || !mounted) return;
    try {
      final result = await widget.app.driverRepository
          .cancelHotelReservation('${item['id']}');
      if (!mounted) return;
      setState(() =>
          _hotelReservations = widget.app.driverRepository.hotelReservations());
      final message = '${result['status']}' == 'refund_pending'
          ? 'Cancellation recorded. Refund awaits finance review.'
          : '${result['status']}' == 'refund_failed'
              ? 'Cancellation recorded, but the refund failed. Contact support.'
              : 'Reservation cancelled.';
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));
    } catch (error) {
      if (mounted)
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$error')));
    }
  }

  Widget _bookingList(List<Booking> bookings, String empty) => bookings.isEmpty
      ? Center(
          child: Padding(
              padding: const EdgeInsets.all(25),
              child: Text(empty,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: VoltColors.muted))))
      : ListView.builder(
          padding: const EdgeInsets.all(16),
          itemCount: bookings.length,
          itemBuilder: (context, index) {
            final booking = bookings[index];
            return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: VoltCard(
                    child: Material(
                        color: Colors.transparent,
                        child: ListTile(
                            contentPadding: EdgeInsets.zero,
                            leading: const CircleAvatar(
                                backgroundColor: VoltColors.elevated,
                                child: Icon(Icons.ev_station,
                                    color: VoltColors.green)),
                            title: Text(booking.vendorName ?? 'Highway pitstop',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w800)),
                            subtitle: Text(
                                '${booking.slotStartTime == null ? 'Time to be confirmed' : '${booking.slotStartTime!.day}/${booking.slotStartTime!.month} • ${_time(booking.slotStartTime)} – ${_time(booking.slotEndTime)}'}\n₹${booking.amountInr.toStringAsFixed(0)} • ${booking.status}',
                                maxLines: 2),
                            trailing: const Icon(Icons.chevron_right),
                            onTap: () => Navigator.push(
                                context,
                                MaterialPageRoute(
                                    builder: (_) => BookingDetailsScreen(
                                        app: widget.app,
                                        booking: booking)))))));
          });
}

class BookingDetailsScreen extends StatefulWidget {
  const BookingDetailsScreen(
      {super.key, required this.app, required this.booking});
  final AppController app;
  final Booking booking;
  @override
  State<BookingDetailsScreen> createState() => _BookingDetailsScreenState();
}

class _BookingDetailsScreenState extends State<BookingDetailsScreen> {
  late Booking _booking;
  bool _busy = false;
  bool _refreshing = false;
  StreamSubscription<void>? _bookingChanges;
  Timer? _fallbackRefresh;
  @override
  void initState() {
    super.initState();
    _booking = widget.booking;
    final repository = widget.app.driverRepository;
    _bookingChanges = repository.watchBooking(_booking.id).listen(
          (_) => _refreshBooking(),
          onError: (_) {},
        );
    _fallbackRefresh = Timer.periodic(
      const Duration(seconds: 30),
      (_) => _refreshBooking(),
    );
  }

  @override
  void dispose() {
    _fallbackRefresh?.cancel();
    _bookingChanges?.cancel();
    super.dispose();
  }

  Future<void> _refreshBooking() async {
    if (_refreshing) return;
    _refreshing = true;
    try {
      final latest = await widget.app.driverRepository.booking(_booking.id);
      if (mounted) {
        setState(() => _booking = latest);
      }
    } catch (_) {
      // Keep the last known server response visible; the timer/manual refresh
      // will retry without clearing confirmed booking details.
    } finally {
      _refreshing = false;
    }
  }

  Future<void> _cancel() async {
    Map<String, dynamic> quote;
    try {
      quote = await widget.app.driverRepository
          .bookingCancellationQuote(_booking.id);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Could not check refund estimate: $error')));
      }
      return;
    }
    final refund = quote['customer_refund_inr'] ?? 0;
    final retained = quote['retained_amount_inr'] ?? 0;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Cancel this booking?'),
        content: Text(
            'Estimated refund: ₹$refund\nRetained amount: ₹$retained\n\nNo extra gateway fee is deducted. The server checks the final amount and eligible refunds are reviewed by finance.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Keep booking')),
          FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Cancel booking')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _busy = true);
    try {
      _booking = await widget.app.driverRepository.cancelBooking(_booking.id);
      if (mounted) setState(() {});
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$error')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: const Text('Booking details'), actions: [
        IconButton(
            tooltip: 'Refresh booking status',
            onPressed: _refreshBooking,
            icon: const Icon(Icons.refresh_rounded))
      ]),
      body: ListView(padding: const EdgeInsets.all(18), children: [
        VoltCard(
            child: Column(children: [
          Icon(
              _serviceIcon(_booking.serviceType ?? _booking.vendorType ?? ''),
              color: VoltColors.green,
              size: 40),
          const SizedBox(height: 10),
          Text(_booking.status.toUpperCase(),
              style: const TextStyle(
                  color: VoltColors.green, fontWeight: FontWeight.w900)),
          const SizedBox(height: 14),
          _ReviewRow(
              label: 'Booking reference',
              value: '#${_booking.id.length > 8 ? _booking.id.substring(0, 8).toUpperCase() : _booking.id.toUpperCase()}'),
          _ReviewRow(label: 'Pitstop', value: _booking.vendorName ?? 'VoltStop partner'),
          if (_booking.vendorAddress != null)
            _ReviewRow(label: 'Address', value: _booking.vendorAddress!),
          if (_booking.serviceType != null)
            _ReviewRow(
                label: 'Booked service',
                value: _serviceName(_booking.serviceType!)),
          _ReviewRow(
              label: 'Date',
              value: _booking.slotStartTime == null
                  ? 'Time to be confirmed'
                  : '${_booking.slotStartTime!.day}/${_booking.slotStartTime!.month}/${_booking.slotStartTime!.year}'),
          _ReviewRow(
              label: 'Time',
              value:
                  '${_time(_booking.slotStartTime)} – ${_time(_booking.slotEndTime)}'),
          _ReviewRow(
              label: 'Amount',
              value: '₹${_booking.amountInr.toStringAsFixed(0)}'),
          _ReviewRow(
              label: 'Payment', value: _booking.paymentStatus ?? 'Pending')
        ])),
        if (_booking.status == 'confirmed') ...[
          const SizedBox(height: 14),
          VoltCard(
              child: Column(children: [
            QrImageView(
                data: _booking.id, size: 150, backgroundColor: Colors.white),
            const SizedBox(height: 10),
            const Text('Booking reference QR',
                style: TextStyle(fontWeight: FontWeight.w800)),
            const SizedBox(height: 5),
            const Text(
                'Reference only — QR gate validation is not yet available.',
                textAlign: TextAlign.center,
                style: TextStyle(color: VoltColors.muted, fontSize: 11))
          ]))
        ],
        const SizedBox(height: 14),
        OutlinedButton.icon(
            onPressed: () => _directions(context),
            icon: const Icon(Icons.directions),
            label: const Text('Directions to pitstop')),
        if (_booking.status == 'pending' || _booking.status == 'confirmed')
          FilledButton.tonalIcon(
              onPressed: _busy ? null : _cancel,
              icon: const Icon(Icons.cancel_outlined),
              label: Text(_busy ? 'Cancelling…' : 'Cancel booking')),
        if (_booking.status == 'confirmed' ||
            _booking.status == 'completed' ||
            _booking.status == 'cancelled')
          OutlinedButton.icon(
            onPressed: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) =>
                      CreateDisputeScreen(app: widget.app, booking: _booking),
                )),
            icon: const Icon(Icons.support_agent),
            label: const Text('Report a booking issue'),
          ),
      ]));

  Future<void> _directions(BuildContext context) async {
    if (_booking.vendorLat == null || _booking.vendorLng == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('This pitstop has no map location yet.')));
      return;
    }
    await Navigator.push(
        context,
        MaterialPageRoute(
            builder: (_) => DestinationMapScreen(
                latitude: _booking.vendorLat!,
                longitude: _booking.vendorLng!,
                title: _booking.vendorName ?? 'VoltStop pitstop',
                address: _booking.vendorAddress,
                serviceType:
                    _booking.serviceType ?? _booking.vendorType ?? '')));
  }
}

class DestinationMapScreen extends StatefulWidget {
  const DestinationMapScreen({
    super.key,
    required this.latitude,
    required this.longitude,
    required this.title,
    required this.serviceType,
    this.address,
  });
  final double latitude;
  final double longitude;
  final String title;
  final String? address;
  final String serviceType;

  @override
  State<DestinationMapScreen> createState() => _DestinationMapScreenState();
}

class _DestinationMapScreenState extends State<DestinationMapScreen> {
  final MapController _mapController = MapController();
  List<LatLng> _route = const [];
  LatLng? _origin;
  bool _loading = true;
  bool _mapReady = false;
  String? _message;

  LatLng get _destination =>
      LatLng(widget.latitude, widget.longitude);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadRoute());
  }

  Future<void> _loadRoute() async {
    if (!mounted) return;
    setState(() {
      _loading = true;
      _message = null;
      _route = const [];
    });
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        throw const _LocationFailure('Turn on location to show a route.');
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        throw const _LocationFailure(
            'Allow location access to show directions from your current position.');
      }
      final position = await Geolocator.getCurrentPosition(
          locationSettings: const LocationSettings(
              accuracy: LocationAccuracy.medium,
              timeLimit: Duration(seconds: 12)));
      final origin = LatLng(position.latitude, position.longitude);
      final url = Uri.parse(
          '${AppConfig.osrmRouterUrl}/${origin.longitude},${origin.latitude};${_destination.longitude},${_destination.latitude}');
      final response = await Dio().getUri(url.replace(queryParameters: {
        'overview': 'full',
        'geometries': 'geojson',
        'steps': 'false',
      }), options: Options(receiveTimeout: const Duration(seconds: 15)));
      final data = response.data;
      final routes = data is Map ? data['routes'] : null;
      final geometry = routes is List && routes.isNotEmpty
          ? (routes.first is Map ? routes.first['geometry'] : null)
          : null;
      final coordinates = geometry is Map ? geometry['coordinates'] : null;
      final points = coordinates is List
          ? coordinates
              .whereType<List>()
              .where((point) => point.length >= 2)
              .map((point) => LatLng(
                  (point[1] as num).toDouble(), (point[0] as num).toDouble()))
              .toList()
          : <LatLng>[];
      if (points.length < 2) {
        throw const FormatException('A route was not returned.');
      }
      if (!mounted) return;
      setState(() {
        _origin = origin;
        _route = points;
        _loading = false;
        _message = 'Route preview · follow road signs and local traffic rules.';
      });
      _fitRoute();
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _message = error is _LocationFailure
            ? error.message
            : 'Could not load a driving route. The pitstop location is still shown on the map.';
      });
      if (_mapReady) _mapController.move(_destination, 13);
    }
  }

  void _fitRoute() {
    if (!_mapReady || _route.length < 2) return;
    _mapController.fitCamera(CameraFit.bounds(
        bounds: LatLngBounds.fromPoints(_route),
        padding: const EdgeInsets.fromLTRB(32, 32, 32, 210)));
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: const Text('Directions to pitstop')),
      body: Stack(children: [
        FlutterMap(
          mapController: _mapController,
          options: MapOptions(
              initialCenter: _destination,
              initialZoom: 13,
              onMapReady: () {
                _mapReady = true;
                _fitRoute();
              }),
          children: [
            TileLayer(
                urlTemplate: AppConfig.osmTileUrl,
                userAgentPackageName: 'com.voltstop.app'),
            if (_route.length > 1)
              PolylineLayer(polylines: [
                Polyline(
                    points: _route,
                    color: VoltColors.green,
                    strokeWidth: 5,
                    borderColor: Colors.white,
                    borderStrokeWidth: 2)
              ]),
            MarkerLayer(markers: [
              Marker(
                  point: _destination,
                  width: 52,
                  height: 52,
                  child: Icon(_serviceIcon(widget.serviceType),
                      color: VoltColors.forest, size: 38)),
              if (_origin != null)
                Marker(
                    point: _origin!,
                    width: 42,
                    height: 42,
                    child: const Icon(Icons.my_location,
                        color: VoltColors.cyan, size: 28)),
            ]),
            RichAttributionWidget(attributions: [
              TextSourceAttribution('OpenStreetMap contributors',
                  onTap: () => launchUrl(
                      Uri.parse('https://openstreetmap.org/copyright'))),
            ]),
          ],
        ),
        Positioned(
            left: 14,
            right: 14,
            bottom: 16,
            child: VoltCard(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(widget.title,
                          style: const TextStyle(
                              fontWeight: FontWeight.w900, fontSize: 17)),
                      if (widget.address?.isNotEmpty ?? false)
                        Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Text(widget.address!,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                    color: VoltColors.muted))),
                      if (_message != null)
                        Padding(
                            padding: const EdgeInsets.only(top: 8),
                            child: Text(_message!,
                                style: const TextStyle(
                                    color: VoltColors.muted, fontSize: 12))),
                      const SizedBox(height: 8),
                      SizedBox(
                          width: double.infinity,
                          child: FilledButton.icon(
                              onPressed: _loading ? null : _loadRoute,
                              icon: _loading
                                  ? const SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(
                                          strokeWidth: 2))
                                  : const Icon(Icons.route_rounded),
                              label: Text(_loading
                                  ? 'Loading route…'
                                  : _route.isEmpty
                                      ? 'Try loading route'
                                      : 'Refresh route')))
                    ])))
      ]));
}

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key, required this.app});
  final AppController app;
  @override
  Widget build(BuildContext context) {
    final profile = app.profile;
    final displayName = profile?.name?.trim() ?? '';
    return ListView(
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 30),
        children: [
          const BrandMark(compact: true),
          const SizedBox(height: 22),
          const VoltPageHeading(
            eyebrow: 'Your account',
            title: 'Driver profile',
            subtitle: 'Your details and saved vehicle information.',
          ),
          const SizedBox(height: 18),
          Container(
            padding: const EdgeInsets.all(19),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(VoltRadii.card + 3),
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [Color(0xFF214F40), Color(0xFF173B32)],
              ),
              boxShadow: const [
                BoxShadow(
                    color: Color(0x17183E32),
                    blurRadius: 18,
                    offset: Offset(0, 8))
              ],
            ),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                CircleAvatar(
                  radius: 25,
                  backgroundColor: const Color(0x24FFFFFF),
                  child: Text(
                    (displayName.isNotEmpty ? displayName[0] : 'V')
                        .toUpperCase(),
                    style: const TextStyle(
                        color: VoltColors.lime,
                        fontSize: 20,
                        fontWeight: FontWeight.w800),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(profile?.name ?? 'Driver profile',
                            style: Theme.of(context)
                                .textTheme
                                .titleLarge
                                ?.copyWith(color: VoltColors.surface)),
                        const SizedBox(height: 3),
                        Text(profile?.phone ?? 'Phone verified with Supabase',
                            style: const TextStyle(
                                color: Color(0xFFD5E1D7), fontSize: 12)),
                      ]),
                ),
                const Icon(Icons.verified_user_outlined,
                    color: VoltColors.lime, size: 20),
              ]),
              const SizedBox(height: 17),
              Container(height: 1, color: const Color(0x2FFFFFFF)),
              const SizedBox(height: 13),
              Row(children: [
                Expanded(
                    child: _profileMetric(
                        'VEHICLE', profile?.carModel ?? 'Not set')),
                const SizedBox(width: 12),
                Expanded(
                    child: _profileMetric(
                        'BATTERY', '${profile?.batteryKwh ?? '—'} kWh')),
                const SizedBox(width: 12),
                Expanded(
                    child: _profileMetric('EFFICIENCY',
                        '${profile?.efficiencyKmPerKwh ?? '—'} km/kWh')),
              ]),
            ]),
          ),
          const SizedBox(height: 20),
          Text('YOUR GARAGE',
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                  fontSize: 10, letterSpacing: 1.1, color: VoltColors.muted)),
          const SizedBox(height: 9),
          VoltCard(
              padding: EdgeInsets.zero,
              child: Column(children: [
                _ProfileActionTile(
                  icon: Icons.directions_car_outlined,
                  title: 'My vehicles',
                  subtitle: app.activeVehicle?.displayName ??
                      '${app.vehicles.length} saved vehicles',
                  onTap: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => VehiclesScreen(app: app))),
                ),
                const Divider(height: 1, indent: 68),
                _ProfileActionTile(
                  icon: Icons.tune_rounded,
                  title: 'Vehicle profile',
                  subtitle: 'Update efficiency and battery details',
                  onTap: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => ProfileSetupScreen(app: app))),
                ),
                const Divider(height: 1, indent: 68),
                _ProfileActionTile(
                  icon: Icons.history_rounded,
                  title: 'Booking history',
                  subtitle: 'Your upcoming and past reservations',
                  onTap: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) => Scaffold(
                              appBar:
                                  AppBar(title: const Text('Booking history')),
                              body: BookingsScreen(app: app)))),
                ),
              ])),
          const SizedBox(height: 19),
          OutlinedButton.icon(
            onPressed: () async {
              await app.logout();
              if (context.mounted)
                Navigator.of(context).pushAndRemoveUntil(
                    MaterialPageRoute(
                        builder: (_) => OnboardingScreen(app: app)),
                    (_) => false);
            },
            icon: const Icon(Icons.logout_rounded),
            label: const Text('Sign out'),
          ),
          const SizedBox(height: 14),
          const Text(
              'VoltStop NH–16 pilot  ·  Route and battery figures are estimates.',
              textAlign: TextAlign.center,
              style: TextStyle(color: VoltColors.muted, fontSize: 11)),
        ]);
  }

  Widget _profileMetric(String label, String value) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: const TextStyle(
                  color: Color(0xFFBFD0C6),
                  fontSize: 8,
                  letterSpacing: .8,
                  fontWeight: FontWeight.w800)),
          const SizedBox(height: 4),
          Text(value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                  color: VoltColors.surface,
                  fontSize: 11,
                  fontWeight: FontWeight.w700)),
        ],
      );
}

class _ProfileActionTile extends StatelessWidget {
  const _ProfileActionTile(
      {required this.icon,
      required this.title,
      required this.subtitle,
      required this.onTap});
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 13, vertical: 4),
        leading: VoltIconBadge(icon: icon, size: 40),
        title: Text(title, style: Theme.of(context).textTheme.titleSmall),
        subtitle: Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
        trailing:
            const Icon(Icons.chevron_right_rounded, color: VoltColors.muted),
        onTap: onTap,
      );
}
