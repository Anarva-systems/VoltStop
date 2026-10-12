import 'dart:math';

import 'package:flutter/material.dart';

import '../../../controllers/app_controller.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/volt_widgets.dart';
import '../../../models/booking.dart';

class DisputesScreen extends StatefulWidget {
  const DisputesScreen({super.key, required this.app});

  final AppController app;

  @override
  State<DisputesScreen> createState() => _DisputesScreenState();
}

class _DisputesScreenState extends State<DisputesScreen> {
  late Future<List<Map<String, dynamic>>> _disputes;

  @override
  void initState() {
    super.initState();
    _disputes = widget.app.driverRepository.disputes();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('My disputes')),
        body: FutureBuilder<List<Map<String, dynamic>>>(
          future: _disputes,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const VoltLoading(label: 'Loading disputes…');
            }
            if (snapshot.hasError) {
              return Padding(
                padding: const EdgeInsets.all(18),
                child: VoltError(
                  message: '${snapshot.error}',
                  onRetry: () => setState(
                      () => _disputes = widget.app.driverRepository.disputes()),
                ),
              );
            }
            final items = snapshot.data ?? const <Map<String, dynamic>>[];
            if (items.isEmpty) {
              return const Center(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Text(
                      'Disputes for eligible bookings will appear here.',
                      textAlign: TextAlign.center),
                ),
              );
            }
            return ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: items.length,
              itemBuilder: (context, index) {
                final item = items[index];
                return Card(
                  child: ListTile(
                    title: Text('${item['reason'] ?? 'Booking dispute'}'),
                    subtitle: Text(
                        'Booking ${item['booking_id'] ?? '—'}\nStatus: ${item['status'] ?? '—'}'),
                    isThreeLine: true,
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => DisputeDetailsScreen(
                          app: widget.app,
                          disputeId: '${item['id']}',
                        ),
                      ),
                    ),
                  ),
                );
              },
            );
          },
        ),
      );
}

class DisputeDetailsScreen extends StatefulWidget {
  const DisputeDetailsScreen(
      {super.key, required this.app, required this.disputeId});

  final AppController app;
  final String disputeId;

  @override
  State<DisputeDetailsScreen> createState() => _DisputeDetailsScreenState();
}

class _DisputeDetailsScreenState extends State<DisputeDetailsScreen> {
  final _message = TextEditingController();
  late Future<Map<String, dynamic>> _dispute;
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    _dispute = widget.app.driverRepository.dispute(widget.disputeId);
  }

  @override
  void dispose() {
    _message.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final text = _message.text.trim();
    if (text.length < 4 || _sending) return;
    setState(() => _sending = true);
    try {
      await widget.app.driverRepository.addDisputeMessage(
        disputeId: widget.disputeId,
        message: text,
        idempotencyKey: _idempotencyKey(),
      );
      if (!mounted) return;
      _message.clear();
      setState(() =>
          _dispute = widget.app.driverRepository.dispute(widget.disputeId));
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Message sent.')));
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$error')));
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Dispute details')),
        body: FutureBuilder<Map<String, dynamic>>(
          future: _dispute,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const VoltLoading(label: 'Loading dispute…');
            }
            if (snapshot.hasError) {
              return Padding(
                padding: const EdgeInsets.all(18),
                child: VoltError(
                  message: '${snapshot.error}',
                  onRetry: () => setState(() => _dispute =
                      widget.app.driverRepository.dispute(widget.disputeId)),
                ),
              );
            }
            final data = snapshot.data ?? const <String, dynamic>{};
            final timeline = data['timeline'] is List
                ? (data['timeline'] as List).whereType<Map>().toList()
                : const <Map>[];
            return ListView(padding: const EdgeInsets.all(18), children: [
              VoltCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${data['reason'] ?? 'Booking dispute'}',
                        style: Theme.of(context).textTheme.titleLarge),
                    const SizedBox(height: 8),
                    Text('Status: ${data['status'] ?? '—'}'),
                    Text('Booking: ${data['booking_id'] ?? '—'}'),
                    if (data['description'] != null) ...[
                      const Divider(height: 24),
                      Text('${data['description']}'),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: 16),
              Text('Updates', style: Theme.of(context).textTheme.titleMedium),
              if (timeline.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(12),
                  child: Text('No updates yet.',
                      style: TextStyle(color: VoltColors.muted)),
                ),
              ...timeline.map((event) => ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.forum_outlined,
                        color: VoltColors.cyan),
                    title: Text('${event['event_type'] ?? 'Update'}'),
                    subtitle: Text('${event['message'] ?? ''}'),
                  )),
              const SizedBox(height: 12),
              TextField(
                controller: _message,
                minLines: 2,
                maxLines: 5,
                maxLength: 4000,
                decoration: const InputDecoration(
                    labelText: 'Add a message', alignLabelWithHint: true),
              ),
              FilledButton(
                onPressed: _sending ? null : _send,
                child: _sending
                    ? const CircularProgressIndicator()
                    : const Text('Send message'),
              ),
            ]);
          },
        ),
      );
}

class CreateDisputeScreen extends StatefulWidget {
  const CreateDisputeScreen(
      {super.key, required this.app, required this.booking});

  final AppController app;
  final Booking booking;

  @override
  State<CreateDisputeScreen> createState() => _CreateDisputeScreenState();
}

class _CreateDisputeScreenState extends State<CreateDisputeScreen> {
  final _reason = TextEditingController();
  final _description = TextEditingController();
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _reason.dispose();
    _description.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final reason = _reason.text.trim();
    final description = _description.text.trim();
    if (reason.length < 3 || description.length < 8 || _submitting) {
      setState(() => _error =
          'Enter a reason (at least 3 characters) and details (at least 8 characters).');
      return;
    }
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final result = await widget.app.driverRepository.createDispute(
        bookingId: widget.booking.id,
        reason: reason,
        description: description,
        idempotencyKey: _idempotencyKey(),
      );
      if (!mounted) return;
      final id = result['id']?.toString();
      if (id == null || id.isEmpty) {
        throw const FormatException('The server did not return a dispute ID.');
      }
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => DisputeDetailsScreen(app: widget.app, disputeId: id),
        ),
      );
    } catch (error) {
      if (mounted) setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Contact VoltStop')),
        body: ListView(padding: const EdgeInsets.all(18), children: [
          VoltCard(
            child: Text(
                'Create a dispute for booking ${widget.booking.id}. The team will review your request.'),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _reason,
            maxLength: 160,
            decoration: const InputDecoration(labelText: 'Reason'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _description,
            minLines: 4,
            maxLines: 8,
            maxLength: 4000,
            decoration: const InputDecoration(
                labelText: 'Describe what happened', alignLabelWithHint: true),
          ),
          if (_error != null) ...[
            const SizedBox(height: 10),
            Text(_error!, style: const TextStyle(color: VoltColors.red)),
          ],
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _submitting ? null : _submit,
            child: _submitting
                ? const CircularProgressIndicator()
                : const Text('Submit dispute'),
          ),
        ]),
      );
}

String _idempotencyKey() {
  final random = Random.secure();
  final bytes = List<int>.generate(24, (_) => random.nextInt(256));
  return bytes.map((byte) => byte.toRadixString(16).padLeft(2, '0')).join();
}
