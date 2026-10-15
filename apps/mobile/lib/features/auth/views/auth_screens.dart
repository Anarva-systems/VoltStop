import 'dart:async';

import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../../../core/config/app_config.dart';
import '../../../core/services/api_client.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/volt_widgets.dart';
import '../../../controllers/app_controller.dart';
import '../../driver/views/driver_screens.dart';

class OnboardingScreen extends StatelessWidget {
  const OnboardingScreen({super.key, required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(
          child: LayoutBuilder(
            builder: (context, constraints) {
              final compact = constraints.maxHeight < 700;
              return SingleChildScrollView(
                child: ConstrainedBox(
                  constraints: BoxConstraints(minHeight: constraints.maxHeight),
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(24, 14, 24, 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Row(
                          children: [
                            const BrandMark(),
                            const Spacer(),
                            const Icon(
                              Icons.route_outlined,
                              size: 17,
                              color: VoltColors.forest,
                            ),
                            const SizedBox(width: 6),
                            Text(
                              'DRIVER APP',
                              style: Theme.of(context)
                                  .textTheme
                                  .labelLarge
                                  ?.copyWith(fontSize: 10, letterSpacing: 1.1),
                            ),
                          ],
                        ),
                        Padding(
                          padding: EdgeInsets.symmetric(
                            vertical: compact ? 26 : 38,
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'EV TRAVEL, THOUGHTFULLY PLANNED',
                                style: Theme.of(context)
                                    .textTheme
                                    .labelLarge
                                    ?.copyWith(
                                      fontSize: 10,
                                      letterSpacing: 1.15,
                                      color: VoltColors.muted,
                                    ),
                              ),
                              const SizedBox(height: 13),
                              Text(
                                'Your next stop,\nwell chosen.',
                                style: Theme.of(context)
                                    .textTheme
                                    .displaySmall
                                    ?.copyWith(fontSize: compact ? 36 : 40),
                              ),
                              const SizedBox(height: 13),
                              ConstrainedBox(
                                constraints:
                                    const BoxConstraints(maxWidth: 330),
                                child: Text(
                                  'Plan charging, food and rest around the road ahead — then reserve a stop before you arrive.',
                                  style: Theme.of(context)
                                      .textTheme
                                      .bodyLarge
                                      ?.copyWith(
                                        color: VoltColors.muted,
                                        height: 1.5,
                                      ),
                                ),
                              ),
                              SizedBox(height: compact ? 20 : 26),
                              const _PilotRouteCard(),
                            ],
                          ),
                        ),
                        Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            VoltButton(
                              label: 'Continue with phone',
                              icon: Icons.arrow_forward_rounded,
                              onPressed: () => _openAuth(context),
                            ),
                            const SizedBox(height: 3),
                            Center(
                              child: TextButton(
                                onPressed: () => _openAuth(context),
                                child: const Text(
                                  'Already have an account?  Sign in',
                                ),
                              ),
                            ),
                            const SizedBox(height: 1),
                            Text(
                              'SECURE PHONE SIGN-IN',
                              style: Theme.of(context)
                                  .textTheme
                                  .labelLarge
                                  ?.copyWith(
                                    fontSize: 9,
                                    letterSpacing: 1.2,
                                    color: VoltColors.muted,
                                  ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      );

  void _openAuth(BuildContext context) => Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => PhoneAuthScreen(app: app)),
      );
}

class _PilotRouteCard extends StatelessWidget {
  const _PilotRouteCard();

  @override
  Widget build(BuildContext context) => VoltCard(
        padding: const EdgeInsets.fromLTRB(16, 15, 16, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(
                  'PILOT CORRIDOR',
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                        fontSize: 10,
                        letterSpacing: 1.05,
                        color: VoltColors.muted,
                      ),
                ),
                const Spacer(),
                Container(
                  width: 7,
                  height: 7,
                  decoration: const BoxDecoration(
                    color: VoltColors.lime,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 7),
                Text(
                  'NH–16',
                  style: Theme.of(context)
                      .textTheme
                      .labelLarge
                      ?.copyWith(color: VoltColors.forest),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Column(
                  children: [
                    _RouteNode(color: VoltColors.forest),
                    Container(width: 1.5, height: 23, color: VoltColors.border),
                    _RouteNode(color: VoltColors.lime, outlined: true),
                  ],
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Srikakulam',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        'Andhra Pradesh',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Vijayawada',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ],
                  ),
                ),
                Container(
                  width: 36,
                  height: 36,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: VoltColors.elevated,
                    borderRadius: BorderRadius.circular(11),
                  ),
                  child: const Icon(
                    Icons.ev_station_outlined,
                    size: 19,
                    color: VoltColors.forest,
                  ),
                ),
              ],
            ),
          ],
        ),
      );
}

class _RouteNode extends StatelessWidget {
  const _RouteNode({required this.color, this.outlined = false});
  final Color color;
  final bool outlined;

  @override
  Widget build(BuildContext context) => Container(
        width: 9,
        height: 9,
        decoration: BoxDecoration(
          color: outlined ? VoltColors.surface : color,
          shape: BoxShape.circle,
          border: Border.all(color: VoltColors.forest, width: 1.5),
        ),
      );
}

class PhoneAuthScreen extends StatefulWidget {
  const PhoneAuthScreen({super.key, required this.app});
  final AppController app;
  @override
  State<PhoneAuthScreen> createState() => _PhoneAuthScreenState();
}

class _PhoneAuthScreenState extends State<PhoneAuthScreen> {
  final _phone = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _phone.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final phone = _normalizeIndianPhone(_phone.text);
    if (phone == null) {
      setState(
        () => _error =
            'Enter a valid Indian mobile number with 10 digits (starting 6–9).',
      );
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.app.checkApiReadiness();
      await widget.app.auth.sendOtp(phone);
      if (!mounted) return;
      unawaited(
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => OtpScreen(app: widget.app, phone: phone),
          ),
        ),
      );
    } catch (error) {
      if (mounted) setState(() => _error = _authError(error, sending: true));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const BrandMark(compact: true)),
        body: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: ListView(
                padding: const EdgeInsets.fromLTRB(24, 20, 24, 28),
                children: [
                  Text(
                    'DRIVER ACCESS',
                    style: Theme.of(context).textTheme.labelLarge?.copyWith(
                          fontSize: 10,
                          letterSpacing: 1.15,
                          color: VoltColors.muted,
                        ),
                  ),
                  const SizedBox(height: 13),
                  Text(
                    'Sign in, then hit the road.',
                    style: Theme.of(context)
                        .textTheme
                        .headlineMedium
                        ?.copyWith(fontSize: 32),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'Enter the mobile number on your VoltStop account to request a one-time code. Delivery depends on the authentication service and SMS provider.',
                    style: Theme.of(context)
                        .textTheme
                        .bodyLarge
                        ?.copyWith(color: VoltColors.muted),
                  ),
                  const SizedBox(height: 26),
                  TextField(
                    controller: _phone,
                    keyboardType: TextInputType.phone,
                    textInputAction: TextInputAction.done,
                    onSubmitted: (_) => _send(),
                    decoration: const InputDecoration(
                      labelText: 'Mobile number',
                      prefixText: '+91  ',
                      hintText: '98765 43210',
                    ),
                  ),
                  const SizedBox(height: 7),
                  Text(
                    'India  ·  10-digit number',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  if (!AppConfig.hasSupabase) ...[
                    const SizedBox(height: 15),
                    VoltCard(
                      padding: const EdgeInsets.all(13),
                      color: VoltColors.elevated,
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(
                            Icons.info_outline,
                            size: 19,
                            color: VoltColors.warning,
                          ),
                          const SizedBox(width: 9),
                          Expanded(
                            child: Text(
                              'Phone verification is not connected in this build.',
                              style: Theme.of(context)
                                  .textTheme
                                  .bodySmall
                                  ?.copyWith(color: VoltColors.text),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!,
                        style: const TextStyle(color: VoltColors.red)),
                  ],
                  const SizedBox(height: 22),
                  VoltButton(
                    label: 'Request one-time code',
                    icon: Icons.sms_outlined,
                    onPressed: _send,
                    busy: _busy,
                  ),
                  const SizedBox(height: 14),
                  Text(
                    'Your number is used only to secure access to your driver account.',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          ),
        ),
      );
}

class OtpScreen extends StatefulWidget {
  const OtpScreen({super.key, required this.app, required this.phone});
  final AppController app;
  final String phone;
  @override
  State<OtpScreen> createState() => _OtpScreenState();
}

class _OtpScreenState extends State<OtpScreen> {
  static const _resendCooldownSeconds = 60;
  final _code = TextEditingController();
  bool _busy = false;
  bool _authenticated = false;
  int _resendSeconds = _resendCooldownSeconds;
  Timer? _resendTimer;
  String _requestStatus = 'Supabase accepted the OTP request';
  String? _error;

  @override
  void initState() {
    super.initState();
    _startResendCooldown();
  }

  @override
  void dispose() {
    _resendTimer?.cancel();
    _code.dispose();
    super.dispose();
  }

  void _startResendCooldown() {
    _resendTimer?.cancel();
    setState(() => _resendSeconds = _resendCooldownSeconds);
    _resendTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted || _resendSeconds <= 1) {
        timer.cancel();
        if (mounted) setState(() => _resendSeconds = 0);
        return;
      }
      setState(() => _resendSeconds--);
    });
  }

  Future<void> _resend() async {
    if (_busy || _authenticated || _resendSeconds > 0) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    // Apply the local cooldown even when the provider rejects the request.
    // Supabase's server-side rate limit remains authoritative.
    _startResendCooldown();
    try {
      await widget.app.checkApiReadiness();
      await widget.app.auth.sendOtp(widget.phone);
      if (mounted) {
        setState(() => _requestStatus = 'Supabase accepted a new code request');
      }
    } catch (error) {
      if (mounted) setState(() => _error = _authError(error, sending: true));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _verify() async {
    if (_authenticated) {
      await _retryProfile();
      return;
    }
    final token = _code.text.trim();
    if (!RegExp(r'^\d{6}$').hasMatch(token)) {
      setState(() => _error = 'Enter the six-digit verification code.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      // Do not consume a valid one-time code unless the backend is ready to
      // finish sign-in and load the driver's profile.
      await widget.app.checkApiReadiness();
      await widget.app.auth.verifyOtp(widget.phone, token);
      if (!widget.app.isSignedIn) {
        throw StateError(
          'Verification did not create an authenticated session.',
        );
      }
      _authenticated = true;
      await _loadProfileAndContinue();
    } catch (error) {
      if (mounted) setState(() => _error = _authError(error, sending: false));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _retryProfile() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await _loadProfileAndContinue();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _loadProfileAndContinue() async {
    await widget.app.loadProfile();
    if (!mounted) return;
    if (widget.app.profileLoadError != null) {
      final detail = widget.app.profileLoadError;
      setState(
        () => _error =
            'Your code was verified, but VoltStop could not load your driver profile: ${detail ?? 'profile service unavailable'}. Check that the VoltStop API is reachable, then retry.',
      );
      return;
    }
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(
        builder: (_) => widget.app.profileComplete
            ? DriverShell(app: widget.app)
            : ProfileSetupScreen(app: widget.app),
      ),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const BrandMark(compact: true)),
        body: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: ListView(
                padding: const EdgeInsets.fromLTRB(24, 20, 24, 28),
                children: [
                  Text(
                    'SECURE SIGN-IN',
                    style: Theme.of(context).textTheme.labelLarge?.copyWith(
                          fontSize: 10,
                          letterSpacing: 1.15,
                          color: VoltColors.muted,
                        ),
                  ),
                  const SizedBox(height: 13),
                  Text(
                    'Request accepted',
                    style: Theme.of(context).textTheme.headlineMedium,
                  ),
                  const SizedBox(height: 10),
                  Text(
                    '$_requestStatus for ${widget.phone}. This confirms request processing only; SMS delivery to your device is not confirmed. Verify the number and wait before retrying; rate limits may apply.',
                    style: Theme.of(context)
                        .textTheme
                        .bodyLarge
                        ?.copyWith(color: VoltColors.muted),
                  ),
                  const SizedBox(height: 26),
                  TextField(
                    controller: _code,
                    keyboardType: TextInputType.number,
                    textInputAction: TextInputAction.done,
                    maxLength: 6,
                    decoration: const InputDecoration(
                      labelText: 'Verification code',
                      hintText: '••••••',
                    ),
                    onSubmitted: (_) => _verify(),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 8),
                    Text(_error!,
                        style: const TextStyle(color: VoltColors.red)),
                  ],
                  const SizedBox(height: 18),
                  VoltButton(
                    label: _authenticated
                        ? 'Retry profile loading'
                        : 'Verify and continue',
                    icon: Icons.arrow_forward_rounded,
                    onPressed: _authenticated ? _retryProfile : _verify,
                    busy: _busy,
                  ),
                  Center(
                    child: TextButton.icon(
                      onPressed:
                          _resendSeconds == 0 && !_busy && !_authenticated
                              ? _resend
                              : null,
                      icon: const Icon(Icons.refresh),
                      label: Text(
                        _resendSeconds > 0
                            ? 'Resend code in ${_resendSeconds}s'
                            : 'Resend code',
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Center(
                    child: TextButton(
                      onPressed: () => Navigator.pop(context),
                      child: const Text('Change mobile number'),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
}

String _authError(Object error, {required bool sending}) {
  if (error is ApiException && error.category == 'readiness') {
    return sending
        ? 'VoltStop backend is not ready, so no sign-in code was requested. ${error.message}'
        : 'VoltStop backend is not ready, so your code was not used. ${error.message}';
  }
  if (error is ApiException &&
      sending &&
      {'network', 'timeout', 'dns', 'tls', 'deployment_unavailable'}
          .contains(error.category)) {
    return 'Could not reach the VoltStop backend, so no sign-in code was requested. ${error.message}';
  }
  if (error is ApiException &&
      !sending &&
      {'network', 'timeout', 'dns', 'tls', 'deployment_unavailable'}
          .contains(error.category)) {
    return 'Could not reach the VoltStop backend, so your code was not used. ${error.message}';
  }
  if (error is AuthRetryableFetchException) {
    return 'Could not reach the authentication service. Check your connection and try again.';
  }
  if (error is AuthException) {
    final status = error.statusCode;
    final code = (error.code ?? '').toLowerCase();
    final message = error.message.toLowerCase();
    if (status == '429' ||
        code.contains('rate') ||
        message.contains('rate limit') ||
        message.contains('too many')) {
      return 'Too many code requests. Wait before trying again; a previous request does not confirm delivery.';
    }
    if (sending &&
        message.contains('phone') &&
        (message.contains('invalid') || message.contains('format'))) {
      return 'The authentication service rejected this phone number. Check the country code and 10-digit number.';
    }
    if (sending &&
        (message.contains('sms') ||
            message.contains('provider') ||
            code.contains('provider'))) {
      return 'The SMS provider could not process this request. No message delivery was confirmed; check provider configuration and delivery logs.';
    }
    if (!sending && (message.contains('expired') || code.contains('expired'))) {
      return 'This code has expired. Request a new code and try again.';
    }
    if (!sending && (message.contains('invalid') || code.contains('otp'))) {
      return 'The code was not accepted. Check the six digits or request a new code.';
    }
  }
  return sending
      ? 'The authentication service could not accept this code request. Check your number and connection, then try again.'
      : 'Sign-in could not be completed. Check the code and try again.';
}

String? _normalizeIndianPhone(String value) {
  var digits = value.replaceAll(RegExp(r'\D'), '');
  if (digits.startsWith('0091') && digits.length == 14) {
    digits = digits.substring(4);
  } else if (digits.startsWith('91') && digits.length == 12) {
    digits = digits.substring(2);
  } else if (digits.startsWith('0') && digits.length == 11) {
    digits = digits.substring(1);
  }
  if (!RegExp(r'^[6-9]\d{9}$').hasMatch(digits)) return null;
  return '+91$digits';
}
