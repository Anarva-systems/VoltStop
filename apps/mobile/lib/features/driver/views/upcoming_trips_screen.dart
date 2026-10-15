import 'package:flutter/material.dart';

import '../../../controllers/app_controller.dart';
import '../../../core/services/api_client.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/volt_widgets.dart';
import '../../../models/driver_trip.dart';
import '../../../models/driver_vehicle.dart';
import 'vehicles_screen.dart';

const List<String> nh16PilotStops = [
  'Srikakulam',
  'Vizianagaram',
  'Visakhapatnam',
  'Anakapalle',
  'Tuni',
  'Annavaram',
  'Rajahmundry',
  'Eluru',
  'Vijayawada',
];

class DriverTripsScreen extends StatefulWidget {
  const DriverTripsScreen({
    super.key,
    required this.app,
    required this.reservations,
  });

  final AppController app;
  final Widget reservations;

  @override
  State<DriverTripsScreen> createState() => _DriverTripsScreenState();
}

class _DriverTripsScreenState extends State<DriverTripsScreen> {
  final _myTripsKey = GlobalKey<_MyDriverTripsTabState>();

  Future<void> _createTrip() async {
    if (widget.app.vehicles.isEmpty) {
      final addVehicle = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Add a saved vehicle'),
          content: const Text(
            'Upcoming trips use one of your saved vehicles so VoltStop can keep the vehicle details with the trip.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Later'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Manage vehicles'),
            ),
          ],
        ),
      );
      if (addVehicle == true && mounted) {
        await Navigator.push<void>(
          context,
          MaterialPageRoute(builder: (_) => VehiclesScreen(app: widget.app)),
        );
        if (mounted) setState(() {});
      }
      return;
    }
    final created = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (_) => DriverTripFormScreen(app: widget.app),
      ),
    );
    if (created == true) _myTripsKey.currentState?.reload();
  }

  @override
  Widget build(BuildContext context) => DefaultTabController(
        length: 3,
        child: Scaffold(
          appBar: AppBar(
            title: const Text('Trips'),
            actions: [
              IconButton(
                tooltip: 'Create upcoming trip',
                onPressed: _createTrip,
                icon: const Icon(Icons.add_road),
              ),
            ],
            bottom: const TabBar(
              isScrollable: true,
              tabs: [
                Tab(text: 'My drives'),
                Tab(text: 'Discover'),
                Tab(text: 'Reservations'),
              ],
            ),
          ),
          body: TabBarView(
            children: [
              _MyDriverTripsTab(
                key: _myTripsKey,
                app: widget.app,
                onCreate: _createTrip,
              ),
              _DiscoverDriverTripsTab(app: widget.app),
              widget.reservations,
            ],
          ),
        ),
      );
}

class _MyDriverTripsTab extends StatefulWidget {
  const _MyDriverTripsTab({
    super.key,
    required this.app,
    required this.onCreate,
  });

  final AppController app;
  final VoidCallback onCreate;

  @override
  State<_MyDriverTripsTab> createState() => _MyDriverTripsTabState();
}

class _MyDriverTripsTabState extends State<_MyDriverTripsTab> {
  String _bucket = 'upcoming';
  late Future<List<DriverTrip>> _trips;

  @override
  void initState() {
    super.initState();
    _trips = widget.app.driverRepository.driverTrips();
  }

  void reload() {
    if (!mounted) return;
    setState(() {
      _trips = widget.app.driverRepository.driverTrips(bucket: _bucket);
    });
  }

  Future<void> _refreshTrips() async {
    final next = widget.app.driverRepository.driverTrips(bucket: _bucket);
    if (mounted) setState(() => _trips = next);
    try {
      await next;
    } catch (_) {
      // FutureBuilder renders the retryable error state.
    }
  }

  void _selectBucket(String value) {
    setState(() {
      _bucket = value;
      _trips = widget.app.driverRepository.driverTrips(bucket: value);
    });
  }

  @override
  Widget build(BuildContext context) => Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Row(
              children: [
                Expanded(
                  child: SegmentedButton<String>(
                    segments: const [
                      ButtonSegment(value: 'upcoming', label: Text('Upcoming')),
                      ButtonSegment(value: 'past', label: Text('Past')),
                    ],
                    selected: {_bucket},
                    onSelectionChanged: (selection) {
                      if (selection.isNotEmpty) _selectBucket(selection.first);
                    },
                  ),
                ),
                const SizedBox(width: 8),
                IconButton(
                  tooltip: 'Refresh trips',
                  onPressed: reload,
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),
          ),
          Expanded(
            child: FutureBuilder<List<DriverTrip>>(
              future: _trips,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const VoltLoading(label: 'Loading your drives…');
                }
                if (snapshot.hasError) {
                  return Padding(
                    padding: const EdgeInsets.all(18),
                    child: VoltError(
                      message: _errorText(snapshot.error),
                      onRetry: reload,
                    ),
                  );
                }
                final trips = snapshot.data ?? const <DriverTrip>[];
                if (trips.isEmpty) {
                  return ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.all(18),
                    children: [
                      const SizedBox(height: 40),
                      VoltCard(
                        child: Column(
                          children: [
                            Icon(
                              _bucket == 'upcoming'
                                  ? Icons.route_outlined
                                  : Icons.history,
                              size: 38,
                              color: VoltColors.forest,
                            ),
                            const SizedBox(height: 10),
                            Text(
                              _bucket == 'upcoming'
                                  ? 'No upcoming drives yet'
                                  : 'No past drives to show',
                              style: Theme.of(context).textTheme.titleMedium,
                            ),
                            const SizedBox(height: 6),
                            Text(
                              _bucket == 'upcoming'
                                  ? 'Plan a trip, choose your saved EV, and decide whether to list it for discovery.'
                                  : 'Trips you finish or cancel will appear here.',
                              textAlign: TextAlign.center,
                              style: const TextStyle(color: VoltColors.muted),
                            ),
                            if (_bucket == 'upcoming') ...[
                              const SizedBox(height: 14),
                              FilledButton.icon(
                                onPressed: widget.onCreate,
                                icon: const Icon(Icons.add_road),
                                label: const Text('Plan a trip'),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ],
                  );
                }
                return RefreshIndicator(
                  onRefresh: _refreshTrips,
                  child: ListView.separated(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                    itemCount: trips.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 10),
                    itemBuilder: (context, index) => _DriverTripCard(
                      trip: trips[index],
                      onTap: () async {
                        final changed = await Navigator.push<bool>(
                          context,
                          MaterialPageRoute(
                            builder: (_) => DriverTripDetailsScreen(
                              app: widget.app,
                              trip: trips[index],
                            ),
                          ),
                        );
                        if (changed == true) reload();
                      },
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      );
}

class _DiscoverDriverTripsTab extends StatefulWidget {
  const _DiscoverDriverTripsTab({required this.app});
  final AppController app;

  @override
  State<_DiscoverDriverTripsTab> createState() =>
      _DiscoverDriverTripsTabState();
}

class _DiscoverDriverTripsTabState extends State<_DiscoverDriverTripsTab> {
  String? _origin;
  String? _destination;
  DateTime? _departureOn;
  late Future<List<Map<String, dynamic>>> _trips;

  Future<List<Map<String, dynamic>>> _search() =>
      widget.app.driverRepository.discoverDriverTrips(
        origin: _origin,
        destination: _destination,
        departureOn: _departureOn,
      );

  @override
  void initState() {
    super.initState();
    _trips = _search();
  }

  void _refresh() => setState(() => _trips = _search());

  Future<void> _refreshAndWait() async {
    final next = _search();
    if (mounted) setState(() => _trips = next);
    try {
      await next;
    } catch (_) {
      // FutureBuilder renders the retryable error state.
    }
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final result = await showDatePicker(
      context: context,
      initialDate: _departureOn ?? now,
      firstDate: DateTime(now.year, now.month, now.day),
      lastDate: DateTime(now.year + 2),
    );
    if (result != null) {
      setState(() => _departureOn = result);
      await _refreshAndWait();
    }
  }

  @override
  Widget build(BuildContext context) => Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: DropdownButtonFormField<String?>(
                        initialValue: _origin,
                        isExpanded: true,
                        decoration: const InputDecoration(labelText: 'From'),
                        items: [
                          const DropdownMenuItem<String?>(
                            value: null,
                            child: Text('Any start'),
                          ),
                          ...nh16PilotStops
                              .where((stop) => stop != _destination)
                              .map((stop) => DropdownMenuItem<String?>(
                                    value: stop,
                                    child: Text(stop),
                                  )),
                        ],
                        onChanged: (value) => setState(() => _origin = value),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: DropdownButtonFormField<String?>(
                        initialValue: _destination,
                        isExpanded: true,
                        decoration: const InputDecoration(labelText: 'To'),
                        items: [
                          const DropdownMenuItem<String?>(
                            value: null,
                            child: Text('Any destination'),
                          ),
                          ...nh16PilotStops
                              .where((stop) => stop != _origin)
                              .map((stop) => DropdownMenuItem<String?>(
                                    value: stop,
                                    child: Text(stop),
                                  )),
                        ],
                        onChanged: (value) =>
                            setState(() => _destination = value),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: _pickDate,
                        icon: const Icon(Icons.calendar_month_outlined),
                        label: Text(_departureOn == null
                            ? 'Any departure date'
                            : MaterialLocalizations.of(context)
                                .formatMediumDate(_departureOn!)),
                      ),
                    ),
                    if (_departureOn != null)
                      IconButton(
                        tooltip: 'Clear date filter',
                        onPressed: () {
                          setState(() => _departureOn = null);
                          _refresh();
                        },
                        icon: const Icon(Icons.clear),
                      ),
                    const SizedBox(width: 6),
                    FilledButton.icon(
                      onPressed: _refresh,
                      icon: const Icon(Icons.search),
                      label: const Text('Search'),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                const Text(
                  'Browse-only listings. VoltStop does not book seats or process trip payments.',
                  style: TextStyle(color: VoltColors.muted, fontSize: 12),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
          Expanded(
            child: FutureBuilder<List<Map<String, dynamic>>>(
              future: _trips,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const VoltLoading(label: 'Finding listed trips…');
                }
                if (snapshot.hasError) {
                  return Padding(
                    padding: const EdgeInsets.all(18),
                    child: VoltError(
                      message: _errorText(snapshot.error),
                      onRetry: _refresh,
                    ),
                  );
                }
                final trips = snapshot.data ?? const <Map<String, dynamic>>[];
                if (trips.isEmpty) {
                  return ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.all(18),
                    children: const [
                      SizedBox(height: 32),
                      VoltCard(
                        child: Column(
                          children: [
                            Icon(Icons.explore_outlined,
                                color: VoltColors.forest, size: 36),
                            SizedBox(height: 10),
                            Text('No listed trips match these filters.'),
                            SizedBox(height: 5),
                            Text(
                              'Drivers choose whether to list a trip. Seats shown are driver-provided and are not reserved.',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: VoltColors.muted),
                            ),
                          ],
                        ),
                      ),
                    ],
                  );
                }
                return RefreshIndicator(
                  onRefresh: _refreshAndWait,
                  child: ListView.separated(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(16, 6, 16, 24),
                    itemCount: trips.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 10),
                    itemBuilder: (context, index) => _DiscoverTripCard(
                      trip: trips[index],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      );
}

class DriverTripFormScreen extends StatefulWidget {
  const DriverTripFormScreen({super.key, required this.app, this.initial});
  final AppController app;
  final DriverTrip? initial;

  @override
  State<DriverTripFormScreen> createState() => _DriverTripFormScreenState();
}

class _DriverTripFormScreenState extends State<DriverTripFormScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _notes;
  late String _origin;
  late String _destination;
  late DateTime _departureAt;
  DateTime? _estimatedArrivalAt;
  String? _vehicleId;
  double? _currentSoc;
  int _availableSeats = 1;
  bool _isDiscoverable = false;
  bool _includeRouteEstimate = false;
  bool _busy = false;
  String? _error;
  String? _idempotencyKey;

  bool get _editing => widget.initial != null;

  @override
  void initState() {
    super.initState();
    final trip = widget.initial;
    final vehicle =
        trip == null ? widget.app.activeVehicle : _findVehicle(trip.vehicleId);
    _origin = _stopName(trip?.origin) ?? nh16PilotStops.first;
    _destination = _stopName(trip?.destination) ?? nh16PilotStops.last;
    if (_destination == _origin) _destination = nh16PilotStops.last;
    _departureAt =
        trip?.departureAt ?? DateTime.now().add(const Duration(days: 1));
    _estimatedArrivalAt = trip?.estimatedArrivalAt;
    _vehicleId = vehicle?.id;
    _currentSoc = vehicle?.currentSoc ?? widget.app.profile?.currentSoc;
    _includeRouteEstimate = trip?.routePlan != null || _currentSoc != null;
    _availableSeats = trip?.availableSeats ?? 1;
    _isDiscoverable = trip?.isDiscoverable ?? false;
    _notes = TextEditingController(text: trip?.notes ?? '');
  }

  DriverVehicle? _findVehicle(String? id) {
    if (id == null) return widget.app.activeVehicle;
    for (final vehicle in widget.app.vehicles) {
      if (vehicle.id == id) return vehicle;
    }
    return widget.app.activeVehicle;
  }

  String? _stopName(String? value) {
    if (value == null) return null;
    final name = value.split(',').first.trim();
    return nh16PilotStops.contains(name) ? name : null;
  }

  DriverVehicle? _vehicleForId(String? id) {
    for (final vehicle in widget.app.vehicles) {
      if (vehicle.id == id) return vehicle;
    }
    return null;
  }

  @override
  void dispose() {
    _notes.dispose();
    super.dispose();
  }

  void _changed() {
    _idempotencyKey = null;
    _error = null;
  }

  Future<DateTime?> _pickDateTime(DateTime initial,
      {DateTime? notBefore}) async {
    final now = DateTime.now();
    final firstDate = notBefore == null
        ? DateTime(now.year, now.month, now.day)
        : DateTime(notBefore.year, notBefore.month, notBefore.day);
    final pickedDate = await showDatePicker(
      context: context,
      initialDate: initial.isBefore(firstDate) ? firstDate : initial,
      firstDate: firstDate,
      lastDate: DateTime(now.year + 3),
    );
    if (pickedDate == null || !mounted) return null;
    final pickedTime = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(initial),
    );
    if (pickedTime == null) return null;
    return DateTime(
      pickedDate.year,
      pickedDate.month,
      pickedDate.day,
      pickedTime.hour,
      pickedTime.minute,
    );
  }

  String _formatDateTime(DateTime value) {
    final local = value.toLocal();
    final localizations = MaterialLocalizations.of(context);
    return '${localizations.formatMediumDate(local)} · ${localizations.formatTimeOfDay(TimeOfDay.fromDateTime(local))}';
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    if (_origin == _destination) {
      setState(() => _error = 'Choose different start and destination stops.');
      return;
    }
    if (!_departureAt.isAfter(DateTime.now())) {
      setState(() => _error = 'Choose a departure time in the future.');
      return;
    }
    if (_estimatedArrivalAt != null &&
        !_estimatedArrivalAt!.isAfter(_departureAt)) {
      setState(() => _error = 'Estimated arrival must follow departure.');
      return;
    }
    final vehicleId = _vehicleId;
    if (vehicleId == null) {
      setState(() => _error = 'Choose one of your saved vehicles.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final repository = widget.app.driverRepository;
      if (_editing) {
        await repository.updateDriverTrip(
          tripId: widget.initial!.id,
          origin: _origin,
          destination: _destination,
          departureAt: _departureAt,
          estimatedArrivalAt: _estimatedArrivalAt,
          vehicleId: vehicleId,
          currentSoc: _includeRouteEstimate ? _currentSoc : null,
          availableSeats: _availableSeats,
          notes: _notes.text,
          isDiscoverable: _isDiscoverable,
        );
      } else {
        _idempotencyKey ??=
            'driver-trip-${DateTime.now().microsecondsSinceEpoch}';
        await repository.createDriverTrip(
          origin: _origin,
          destination: _destination,
          departureAt: _departureAt,
          estimatedArrivalAt: _estimatedArrivalAt,
          vehicleId: vehicleId,
          currentSoc: _includeRouteEstimate ? _currentSoc : null,
          availableSeats: _availableSeats,
          notes: _notes.text,
          isDiscoverable: _isDiscoverable,
          idempotencyKey: _idempotencyKey!,
        );
      }
      if (mounted) Navigator.pop(context, true);
    } catch (error) {
      if (mounted) setState(() => _error = _errorText(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final vehicle = _vehicleForId(_vehicleId);
    return Scaffold(
      appBar:
          AppBar(title: Text(_editing ? 'Edit upcoming trip' : 'Plan a trip')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(18, 12, 18, 30),
          children: [
            const Text(
              'Schedule your drive along the NH-16 pilot corridor. This creates a driver trip only; it does not reserve seats or charge a fare.',
              style: TextStyle(color: VoltColors.muted),
            ),
            const SizedBox(height: 16),
            VoltCard(
              child: Column(
                children: [
                  DropdownButtonFormField<String>(
                    initialValue: _origin,
                    decoration: const InputDecoration(labelText: 'From'),
                    items: nh16PilotStops
                        .where((stop) => stop != _destination)
                        .map((stop) => DropdownMenuItem(
                              value: stop,
                              child: Text(stop),
                            ))
                        .toList(),
                    onChanged: _busy
                        ? null
                        : (value) {
                            if (value == null) return;
                            setState(() {
                              _origin = value;
                              _changed();
                            });
                          },
                  ),
                  const SizedBox(height: 8),
                  DropdownButtonFormField<String>(
                    initialValue: _destination,
                    decoration: const InputDecoration(labelText: 'To'),
                    items: nh16PilotStops
                        .where((stop) => stop != _origin)
                        .map((stop) => DropdownMenuItem(
                              value: stop,
                              child: Text(stop),
                            ))
                        .toList(),
                    onChanged: _busy
                        ? null
                        : (value) {
                            if (value == null) return;
                            setState(() {
                              _destination = value;
                              _changed();
                            });
                          },
                  ),
                  const SizedBox(height: 14),
                  _DateTimePickerTile(
                    title: 'Departure',
                    value: _formatDateTime(_departureAt),
                    onTap: _busy
                        ? null
                        : () async {
                            final value = await _pickDateTime(_departureAt);
                            if (value != null && mounted) {
                              setState(() {
                                _departureAt = value;
                                _changed();
                              });
                            }
                          },
                  ),
                  _DateTimePickerTile(
                    title: 'Estimated arrival · optional',
                    value: _estimatedArrivalAt == null
                        ? 'Not set'
                        : _formatDateTime(_estimatedArrivalAt!),
                    trailing: _estimatedArrivalAt == null
                        ? null
                        : IconButton(
                            tooltip: 'Clear estimated arrival',
                            onPressed: _busy
                                ? null
                                : () => setState(() {
                                      _estimatedArrivalAt = null;
                                      _changed();
                                    }),
                            icon: const Icon(Icons.clear),
                          ),
                    onTap: _busy
                        ? null
                        : () async {
                            final value = await _pickDateTime(
                              _estimatedArrivalAt ??
                                  _departureAt.add(const Duration(hours: 2)),
                              notBefore: _departureAt,
                            );
                            if (value != null && mounted) {
                              setState(() {
                                _estimatedArrivalAt = value;
                                _changed();
                              });
                            }
                          },
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            VoltCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Vehicle and seats',
                      style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  DropdownButtonFormField<String>(
                    initialValue: _vehicleId,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Saved EV'),
                    items: widget.app.vehicles
                        .map((item) => DropdownMenuItem(
                              value: item.id,
                              child: Text(
                                  '${item.displayName} · ${item.batteryKwh.toStringAsFixed(0)} kWh'),
                            ))
                        .toList(),
                    validator: (value) => value == null
                        ? 'Add and select a saved vehicle.'
                        : null,
                    onChanged: _busy
                        ? null
                        : (value) {
                            setState(() {
                              _vehicleId = value;
                              final selected = _vehicleForId(value);
                              _currentSoc = selected?.currentSoc ??
                                  widget.app.profile?.currentSoc;
                              _includeRouteEstimate = _currentSoc != null;
                              _changed();
                            });
                          },
                  ),
                  const SizedBox(height: 8),
                  DropdownButtonFormField<int>(
                    initialValue: _availableSeats,
                    decoration: const InputDecoration(
                      labelText: 'Seats offered (1–8)',
                    ),
                    items: List.generate(8, (index) => index + 1)
                        .map((count) => DropdownMenuItem(
                              value: count,
                              child: Text(
                                  '$count ${count == 1 ? 'seat' : 'seats'}'),
                            ))
                        .toList(),
                    onChanged: _busy
                        ? null
                        : (value) {
                            if (value == null) return;
                            setState(() {
                              _availableSeats = value;
                              _changed();
                            });
                          },
                  ),
                  if (vehicle != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      '${vehicle.vehicleType.toUpperCase()} · ${vehicle.efficiencyKmPerKwh.toStringAsFixed(1)} km/kWh',
                      style: const TextStyle(color: VoltColors.muted),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 12),
            VoltCard(
              child: Column(
                children: [
                  SwitchListTile.adaptive(
                    contentPadding: EdgeInsets.zero,
                    title:
                        const Text('Calculate EV route and stop suggestions'),
                    subtitle: const Text(
                      'Optional estimate. Charger suggestions come from VoltStop listings and are not a live CPO availability guarantee.',
                    ),
                    value: _includeRouteEstimate,
                    onChanged: _busy
                        ? null
                        : (value) => setState(() {
                              _includeRouteEstimate = value;
                              _changed();
                            }),
                  ),
                  if (_includeRouteEstimate) ...[
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        _currentSoc == null
                            ? 'Choose current battery charge to calculate energy.'
                            : 'Starting charge: ${_currentSoc!.round()}%',
                      ),
                    ),
                    Slider(
                      value: _currentSoc ?? 50,
                      min: 0,
                      max: 100,
                      divisions: 20,
                      label: _currentSoc == null
                          ? 'Choose charge'
                          : '${_currentSoc!.round()}%',
                      onChanged: _busy
                          ? null
                          : (value) => setState(() {
                                _currentSoc = value;
                                _changed();
                              }),
                    ),
                  ],
                  TextField(
                    controller: _notes,
                    maxLength: 1000,
                    minLines: 2,
                    maxLines: 4,
                    decoration: const InputDecoration(
                      labelText: 'Trip notes · optional',
                      hintText: 'Notes are private to you.',
                    ),
                    onChanged: (_) {
                      _idempotencyKey = null;
                      if (_error != null) setState(() => _error = null);
                    },
                  ),
                  SwitchListTile.adaptive(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('List this trip for discovery'),
                    subtitle: const Text(
                      'Other signed-in drivers can see the route, departure, vehicle, and seats offered. Notes and your account details stay private. No seat booking is available.',
                    ),
                    value: _isDiscoverable,
                    onChanged: _busy
                        ? null
                        : (value) => setState(() {
                              _isDiscoverable = value;
                              _changed();
                            }),
                  ),
                ],
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: const TextStyle(color: VoltColors.red)),
            ],
            const SizedBox(height: 16),
            VoltButton(
              label: _editing ? 'Save trip changes' : 'Create upcoming trip',
              icon: _editing ? Icons.save_outlined : Icons.add_road,
              busy: _busy,
              onPressed: _busy ? null : _submit,
            ),
            const SizedBox(height: 8),
            const Text(
              'Departure and arrival times are saved as UTC and shown in your device’s local time.',
              textAlign: TextAlign.center,
              style: TextStyle(color: VoltColors.muted, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}

class DriverTripDetailsScreen extends StatefulWidget {
  const DriverTripDetailsScreen({
    super.key,
    required this.app,
    required this.trip,
  });
  final AppController app;
  final DriverTrip trip;

  @override
  State<DriverTripDetailsScreen> createState() =>
      _DriverTripDetailsScreenState();
}

class _DriverTripDetailsScreenState extends State<DriverTripDetailsScreen> {
  late Future<DriverTrip> _trip;
  bool _busy = false;
  bool _changed = false;

  @override
  void initState() {
    super.initState();
    _trip = widget.app.driverRepository.driverTrip(widget.trip.id);
  }

  Future<void> _reload() async {
    setState(
        () => _trip = widget.app.driverRepository.driverTrip(widget.trip.id));
    await _trip;
  }

  Future<void> _transition(String action) async {
    if (action == 'cancel') {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Cancel this trip?'),
          content: const Text(
            'This will mark the trip as cancelled. Any external travel arrangements are not changed by VoltStop.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Keep trip'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Cancel trip'),
            ),
          ],
        ),
      );
      if (confirmed != true) return;
    }
    setState(() => _busy = true);
    try {
      await widget.app.driverRepository
          .transitionDriverTrip(widget.trip.id, action);
      _changed = true;
      await _reload();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(_errorText(error))),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _edit(DriverTrip trip) async {
    final saved = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (_) => DriverTripFormScreen(app: widget.app, initial: trip),
      ),
    );
    if (saved == true) {
      _changed = true;
      await _reload();
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('Trip details'),
          leading:
              BackButton(onPressed: () => Navigator.pop(context, _changed)),
        ),
        body: FutureBuilder<DriverTrip>(
          future: _trip,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const VoltLoading(label: 'Loading trip details…');
            }
            if (snapshot.hasError || !snapshot.hasData) {
              return Padding(
                padding: const EdgeInsets.all(18),
                child: VoltError(
                  message: _errorText(snapshot.error),
                  onRetry: _reload,
                ),
              );
            }
            final trip = snapshot.data!;
            final editable = trip.status == 'scheduled' &&
                trip.departureAt.isAfter(DateTime.now());
            final route = trip.routePlan;
            return ListView(
              padding: const EdgeInsets.all(18),
              children: [
                VoltCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              '${trip.origin} → ${trip.destination}',
                              style: Theme.of(context).textTheme.titleLarge,
                            ),
                          ),
                          _TripStatusBadge(status: trip.status),
                        ],
                      ),
                      const SizedBox(height: 16),
                      _detailRow('Departure',
                          _formatDateTime(context, trip.departureAt)),
                      if (trip.estimatedArrivalAt != null)
                        _detailRow('Estimated arrival',
                            _formatDateTime(context, trip.estimatedArrivalAt!)),
                      _detailRow('Vehicle', trip.vehicleName),
                      _detailRow('Seats listed', '${trip.availableSeats}'),
                      _detailRow(
                          'Discovery listing',
                          trip.isDiscoverable
                              ? 'Visible to drivers'
                              : 'Private'),
                      if (trip.notes?.isNotEmpty == true) ...[
                        const Divider(height: 22),
                        Text('Private notes',
                            style: Theme.of(context).textTheme.titleSmall),
                        const SizedBox(height: 4),
                        Text(trip.notes!),
                      ],
                      if (trip.startedAt != null)
                        _detailRow('Started',
                            _formatDateTime(context, trip.startedAt!)),
                      if (trip.completedAt != null)
                        _detailRow('Completed',
                            _formatDateTime(context, trip.completedAt!)),
                      if (trip.cancelledAt != null)
                        _detailRow('Cancelled',
                            _formatDateTime(context, trip.cancelledAt!)),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                if (route != null)
                  VoltCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('EV route estimate',
                            style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 8),
                        _detailRow(
                          'Distance',
                          '${(((route['distance_meters'] as num?)?.toDouble() ?? 0) / 1000.0).toStringAsFixed(0)} km',
                        ),
                        _detailRow('Approx. energy',
                            '${route['estimated_consumption_kwh'] ?? '—'} kWh'),
                        _detailRow('Distance source',
                            '${route['distance_source'] ?? '—'}'),
                        const SizedBox(height: 6),
                        const Text(
                          'Route estimates are not traffic-aware. Confirm station status and pricing with the charging provider before travel.',
                          style:
                              TextStyle(color: VoltColors.muted, fontSize: 12),
                        ),
                        if (trip.recommendedPitstops.isNotEmpty) ...[
                          const Divider(height: 22),
                          Text('Suggested stops',
                              style: Theme.of(context).textTheme.titleSmall),
                          ...trip.recommendedPitstops.map((row) {
                            final vendor = row['vendor'] is Map
                                ? Map<String, dynamic>.from(
                                    row['vendor'] as Map)
                                : <String, dynamic>{};
                            return ListTile(
                              contentPadding: EdgeInsets.zero,
                              leading: const Icon(Icons.ev_station,
                                  color: VoltColors.forest),
                              title:
                                  Text('${vendor['name'] ?? 'Charging stop'}'),
                              subtitle: Text(
                                  '${row['distance_km'] ?? '—'} km from route'),
                            );
                          }),
                        ],
                      ],
                    ),
                  )
                else
                  const VoltCard(
                    child: Text(
                      'No route estimate is attached. The trip is still scheduled; route and charging-stop suggestions require the map provider to be available and a starting battery charge.',
                      style: TextStyle(color: VoltColors.muted),
                    ),
                  ),
                const SizedBox(height: 18),
                if (editable)
                  OutlinedButton.icon(
                    onPressed: _busy ? null : () => _edit(trip),
                    icon: const Icon(Icons.edit_outlined),
                    label: const Text('Edit upcoming trip'),
                  ),
                if (trip.status == 'scheduled') ...[
                  FilledButton.icon(
                    onPressed: _busy ? null : () => _transition('start'),
                    icon: const Icon(Icons.play_arrow),
                    label: const Text('Start trip'),
                  ),
                  const SizedBox(height: 8),
                  TextButton.icon(
                    onPressed: _busy ? null : () => _transition('cancel'),
                    icon: const Icon(Icons.cancel_outlined),
                    label: const Text('Cancel trip'),
                    style:
                        TextButton.styleFrom(foregroundColor: VoltColors.red),
                  ),
                ],
                if (trip.status == 'in_progress')
                  FilledButton.icon(
                    onPressed: _busy ? null : () => _transition('complete'),
                    icon: const Icon(Icons.check_circle_outline),
                    label: const Text('Mark trip completed'),
                  ),
              ],
            );
          },
        ),
      );
}

class _DiscoverTripCard extends StatelessWidget {
  const _DiscoverTripCard({required this.trip});
  final Map<String, dynamic> trip;

  @override
  Widget build(BuildContext context) {
    final departure = DateTime.parse('${trip['departure_at']}').toLocal();
    final vehicle =
        '${trip['vehicle_make'] ?? ''} ${trip['vehicle_model'] ?? ''}'.trim();
    final distanceKm = trip['distance_meters'] is num
        ? ((trip['distance_meters'] as num) / 1000).round()
        : null;
    return VoltCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${trip['origin']} → ${trip['destination']}',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          _detailRow('Departure', _formatDateTime(context, departure)),
          if (trip['estimated_arrival_at'] != null)
            _detailRow(
              'Estimated arrival',
              _formatDateTime(
                context,
                DateTime.parse('${trip['estimated_arrival_at']}').toLocal(),
              ),
            ),
          _detailRow('Vehicle', vehicle.isEmpty ? 'EV' : vehicle),
          _detailRow('Seats listed', '${trip['available_seats'] ?? 0}'),
          if (distanceKm != null)
            _detailRow('Approx. route distance', '$distanceKm km'),
          const SizedBox(height: 4),
          const Text(
            'Seats are listed by the driver; they are not reserved in VoltStop.',
            style: TextStyle(color: VoltColors.muted, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _DriverTripCard extends StatelessWidget {
  const _DriverTripCard({required this.trip, required this.onTap});
  final DriverTrip trip;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Semantics(
        button: true,
        label: '${trip.origin} to ${trip.destination}, ${trip.status}',
        child: InkWell(
          borderRadius: BorderRadius.circular(VoltRadii.card),
          onTap: onTap,
          child: VoltCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text('${trip.origin} → ${trip.destination}',
                          style: Theme.of(context).textTheme.titleMedium),
                    ),
                    _TripStatusBadge(status: trip.status),
                  ],
                ),
                const SizedBox(height: 8),
                _detailRow(
                    'Departure', _formatDateTime(context, trip.departureAt)),
                _detailRow('Vehicle', trip.vehicleName),
                _detailRow('Seats listed', '${trip.availableSeats}'),
                if (trip.routePlan?['distance_meters'] is num)
                  _detailRow(
                    'Approx. distance',
                    '${((trip.routePlan!['distance_meters'] as num) / 1000).round()} km',
                  ),
              ],
            ),
          ),
        ),
      );
}

class _TripStatusBadge extends StatelessWidget {
  const _TripStatusBadge({required this.status});
  final String status;

  @override
  Widget build(BuildContext context) {
    final color = switch (status) {
      'in_progress' => VoltColors.warning,
      'completed' => VoltColors.forest,
      'cancelled' => VoltColors.red,
      _ => VoltColors.muted,
    };
    final label = switch (status) {
      'in_progress' => 'In progress',
      'completed' => 'Completed',
      'cancelled' => 'Cancelled',
      _ => 'Scheduled',
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .1),
        borderRadius: BorderRadius.circular(30),
      ),
      child: Text(label,
          style: TextStyle(
              color: color, fontSize: 12, fontWeight: FontWeight.w700)),
    );
  }
}

class _DateTimePickerTile extends StatelessWidget {
  const _DateTimePickerTile({
    required this.title,
    required this.value,
    required this.onTap,
    this.trailing,
  });
  final String title;
  final String value;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => ListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(title),
        subtitle: Text(value),
        trailing: trailing ?? const Icon(Icons.calendar_month_outlined),
        onTap: onTap,
      );
}

Widget _detailRow(String title, String value) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 132,
            child: Text(title, style: const TextStyle(color: VoltColors.muted)),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );

String _formatDateTime(BuildContext context, DateTime value) {
  final local = value.toLocal();
  final localizations = MaterialLocalizations.of(context);
  return '${localizations.formatMediumDate(local)} · ${localizations.formatTimeOfDay(TimeOfDay.fromDateTime(local))}';
}

String _errorText(Object? error) {
  if (error is ApiException) return error.message;
  return 'VoltStop could not load this information. Check your connection and retry.';
}
