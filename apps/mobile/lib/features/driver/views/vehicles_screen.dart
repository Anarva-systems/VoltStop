import 'package:flutter/material.dart';
import '../../../controllers/app_controller.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/volt_widgets.dart';
import '../../../models/driver_vehicle.dart';

class VehiclesScreen extends StatefulWidget {
  const VehiclesScreen({super.key, required this.app});
  final AppController app;

  @override
  State<VehiclesScreen> createState() => _VehiclesScreenState();
}

class _VehiclesScreenState extends State<VehiclesScreen> {
  bool _loading = false;
  String? _error;

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    await widget.app.refreshVehicles();
    if (!mounted) return;
    setState(() {
      _loading = false;
      _error = widget.app.vehicleLoadError;
    });
  }

  Future<void> _edit([DriverVehicle? vehicle]) async {
    final saved = await showDialog<bool>(
      context: context,
      builder: (_) => _VehicleDialog(app: widget.app, vehicle: vehicle),
    );
    if (saved != true || !mounted) return;
    await _refresh();
  }

  Future<void> _select(DriverVehicle vehicle) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await widget.app.driverRepository.selectDefaultVehicle(vehicle.id);
      await widget.app.refreshVehicles();
    } catch (error) {
      _error = '$error';
    }
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _delete(DriverVehicle vehicle) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Remove vehicle?'),
        content:
            Text('Remove ${vehicle.displayName} from your VoltStop garage?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Keep vehicle')),
          FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Remove')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await widget.app.driverRepository.deleteVehicle(vehicle.id);
      await widget.app.refreshVehicles();
    } catch (error) {
      _error = '$error';
    }
    if (mounted) setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('My vehicles'), actions: [
          IconButton(
              tooltip: 'Refresh vehicles',
              onPressed: _loading ? null : _refresh,
              icon: const Icon(Icons.refresh)),
        ]),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: _loading ? null : () => _edit(),
          icon: const Icon(Icons.add),
          label: const Text('Add vehicle'),
        ),
        body: RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(padding: const EdgeInsets.all(18), children: [
            const VoltPageHeading(
              eyebrow: 'Garage',
              title: 'Saved vehicles',
              subtitle:
                  'Choose the default vehicle used for route energy estimates. Charge is saved separately for each vehicle.',
            ),
            if (_loading) const LinearProgressIndicator(),
            if (_error != null)
              Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: VoltInlineError(message: _error!)),
            if (!_loading && widget.app.vehicles.isEmpty)
              Padding(
                  padding: const EdgeInsets.only(top: 18),
                  child: VoltEmptyState(
                    icon: Icons.electric_car_outlined,
                    title: 'No saved vehicles yet.',
                    description:
                        'Add your EV to personalize range and charging estimates.',
                    action: OutlinedButton(
                        onPressed: () => _edit(),
                        child: const Text('Add your first vehicle')),
                  )),
            ...widget.app.vehicles.map((vehicle) => Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: VoltCard(
                      child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                        Row(children: [
                          const VoltIconBadge(icon: Icons.electric_car),
                          const SizedBox(width: 12),
                          Expanded(
                              child: Text(vehicle.displayName,
                                  style:
                                      Theme.of(context).textTheme.titleMedium)),
                          if (vehicle.isDefault)
                            const VoltStatusPill(status: 'Default'),
                        ]),
                        const SizedBox(height: 8),
                        _line('Type', vehicle.vehicleType),
                        _line('Battery',
                            '${vehicle.batteryKwh.toStringAsFixed(1)} kWh'),
                        _line('Efficiency',
                            '${vehicle.efficiencyKmPerKwh.toStringAsFixed(1)} km/kWh'),
                        _line(
                            'Current charge',
                            vehicle.currentSoc == null
                                ? 'Not set'
                                : '${vehicle.currentSoc!.round()}%'),
                        if (vehicle.connectorCompatibility.isNotEmpty)
                          _line('Connectors',
                              vehicle.connectorCompatibility.join(', ')),
                        const SizedBox(height: 4),
                        Wrap(spacing: 8, children: [
                          if (!vehicle.isDefault)
                            TextButton.icon(
                                onPressed:
                                    _loading ? null : () => _select(vehicle),
                                icon: const Icon(Icons.check_circle_outline),
                                label: const Text('Set default')),
                          TextButton.icon(
                              onPressed: _loading ? null : () => _edit(vehicle),
                              icon: const Icon(Icons.edit_outlined),
                              label: const Text('Edit')),
                          TextButton.icon(
                              onPressed:
                                  _loading ? null : () => _delete(vehicle),
                              icon: const Icon(Icons.delete_outline),
                              label: const Text('Remove')),
                        ]),
                      ])),
                )),
            const SizedBox(height: 90),
          ]),
        ),
      );

  Widget _line(String label, String value) => Padding(
        padding: const EdgeInsets.only(top: 3),
        child: Row(children: [
          Expanded(
              child:
                  Text(label, style: const TextStyle(color: VoltColors.muted))),
          Text(value)
        ]),
      );
}

class _VehicleDialog extends StatefulWidget {
  const _VehicleDialog({required this.app, this.vehicle});
  final AppController app;
  final DriverVehicle? vehicle;
  @override
  State<_VehicleDialog> createState() => _VehicleDialogState();
}

class _VehicleDialogState extends State<_VehicleDialog> {
  late final TextEditingController _make;
  late final TextEditingController _model;
  late final TextEditingController _battery;
  late final TextEditingController _efficiency;
  late final TextEditingController _soc;
  String _type = 'car';
  bool _busy = false;
  String? _error;
  final _connectors = <String>{};
  AppController get app => widget.app;
  static const _connectorOptions = [
    'CCS2',
    'Type 2',
    'CHAdeMO',
    'Bharat AC',
    'Bharat DC',
    'Tesla'
  ];

  @override
  void initState() {
    super.initState();
    final vehicle = widget.vehicle;
    _make = TextEditingController(text: vehicle?.make ?? '');
    _model = TextEditingController(text: vehicle?.model ?? '');
    _battery =
        TextEditingController(text: vehicle?.batteryKwh.toString() ?? '');
    _efficiency = TextEditingController(
        text: vehicle?.efficiencyKmPerKwh.toString() ?? '');
    _soc = TextEditingController(text: vehicle?.currentSoc?.toString() ?? '');
    _type = vehicle?.vehicleType ?? 'car';
    _connectors.addAll(vehicle?.connectorCompatibility ?? const []);
  }

  @override
  void dispose() {
    _make.dispose();
    _model.dispose();
    _battery.dispose();
    _efficiency.dispose();
    _soc.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final battery = double.tryParse(_battery.text.trim());
    final efficiency = double.tryParse(_efficiency.text.trim());
    final charge =
        _soc.text.trim().isEmpty ? null : double.tryParse(_soc.text.trim());
    if (_make.text.trim().isEmpty ||
        _model.text.trim().isEmpty ||
        battery == null ||
        battery <= 0 ||
        battery > 500 ||
        efficiency == null ||
        efficiency <= 0 ||
        efficiency > 20 ||
        (_soc.text.trim().isNotEmpty &&
            (charge == null || charge < 0 || charge > 100))) {
      setState(() => _error =
          'Enter make, model, battery up to 500 kWh, efficiency up to 20 km/kWh, and a charge from 0 to 100%.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (widget.vehicle == null) {
        await app.driverRepository.createVehicle(
          make: _make.text,
          model: _model.text,
          vehicleType: _type,
          batteryKwh: battery,
          efficiencyKmPerKwh: efficiency,
          currentSoc: charge,
          connectorCompatibility: _connectors.toList(),
        );
      } else {
        await app.driverRepository.updateVehicle(widget.vehicle!.id, {
          'make': _make.text.trim(),
          'model': _model.text.trim(),
          'vehicle_type': _type,
          'battery_kwh': battery,
          'efficiency_km_per_kwh': efficiency,
          'current_soc': charge,
          'connector_compatibility': _connectors.toList(),
        });
      }
      if (mounted) Navigator.pop(context, true);
    } catch (error) {
      if (mounted)
        setState(() {
          _busy = false;
          _error = '$error';
        });
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.vehicle == null ? 'Add vehicle' : 'Edit vehicle'),
        content: SizedBox(
            width: 440,
            child: SingleChildScrollView(
                child: Column(mainAxisSize: MainAxisSize.min, children: [
              TextField(
                  controller: _make,
                  textCapitalization: TextCapitalization.words,
                  decoration: const InputDecoration(labelText: 'Make')),
              TextField(
                  controller: _model,
                  textCapitalization: TextCapitalization.words,
                  decoration: const InputDecoration(labelText: 'Model')),
              DropdownButtonFormField<String>(
                  initialValue: _type,
                  decoration: const InputDecoration(labelText: 'Vehicle type'),
                  items: const [
                    DropdownMenuItem(value: 'car', child: Text('Car')),
                    DropdownMenuItem(value: 'suv', child: Text('SUV')),
                    DropdownMenuItem(
                        value: 'motorcycle', child: Text('Motorcycle')),
                    DropdownMenuItem(value: 'other', child: Text('Other')),
                  ],
                  onChanged: _busy
                      ? null
                      : (value) {
                          if (value != null) setState(() => _type = value);
                        }),
              TextField(
                  controller: _battery,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(
                      labelText: 'Battery capacity (kWh)')),
              TextField(
                  controller: _efficiency,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration:
                      const InputDecoration(labelText: 'Efficiency (km/kWh)')),
              TextField(
                  controller: _soc,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(
                      labelText: 'Current charge % (optional)')),
              const SizedBox(height: 12),
              Align(
                  alignment: Alignment.centerLeft,
                  child: Text('Compatible connectors',
                      style: Theme.of(context).textTheme.labelLarge)),
              ..._connectorOptions.map((connector) => CheckboxListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: Text(connector),
                    value: _connectors.contains(connector),
                    onChanged: _busy
                        ? null
                        : (enabled) => setState(() {
                              if (enabled == true) {
                                _connectors.add(connector);
                              } else {
                                _connectors.remove(connector);
                              }
                            }),
                  )),
              if (_error != null)
                Align(
                    alignment: Alignment.centerLeft,
                    child: VoltInlineError(message: _error!)),
            ]))),
        actions: [
          TextButton(
              onPressed: _busy ? null : () => Navigator.pop(context, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: _busy ? null : _save,
              child: Text(_busy ? 'Saving…' : 'Save vehicle')),
        ],
      );
}
