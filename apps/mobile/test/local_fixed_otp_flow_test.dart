import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:voltstop_mobile/controllers/app_controller.dart';
import 'package:voltstop_mobile/core/services/api_client.dart';
import 'package:voltstop_mobile/core/theme/app_theme.dart';
import 'package:voltstop_mobile/features/auth/views/auth_screens.dart';
import 'package:voltstop_mobile/features/driver/views/driver_screens.dart';
import 'package:voltstop_mobile/models/booking.dart';
import 'package:voltstop_mobile/models/driver_profile.dart';
import 'package:voltstop_mobile/models/driver_vehicle.dart';
import 'package:voltstop_mobile/models/pitstop.dart';
import 'package:voltstop_mobile/repositories/auth_repository.dart';
import 'package:voltstop_mobile/repositories/driver_repository.dart';
import 'package:voltstop_mobile/main.dart' show VoltStopApp;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    _FixedOtpAuth.persistedSession = null;
  });

  testWidgets('SMS provider rejection is actionable and never says delivered', (
    tester,
  ) async {
    final auth = _FixedOtpAuth(
      const {},
      sendError: const AuthException('SMS provider is unavailable.'),
    );
    final app = AppController(
      auth: auth,
      driverRepository: _ProfileOnlyDriverRepository(),
    );
    await tester.pumpWidget(
      MaterialApp(
        theme: buildVoltStopTheme(),
        home: PhoneAuthScreen(app: app),
      ),
    );
    await tester.enterText(find.byType(TextField), '9876543210');
    await tester.tap(find.text('Request one-time code'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(
      find.textContaining('SMS provider could not process this request'),
      findsOneWidget,
    );
    expect(find.text('Request accepted'), findsNothing);
    expect(find.text('OTP sent'), findsNothing);
  });

  testWidgets(
    'OTP resend waits for cooldown and reports acceptance accurately',
    (tester) async {
      final auth = _FixedOtpAuth({'+919876543210': '123456'});
      final app = AppController(
        auth: auth,
        driverRepository: _ProfileOnlyDriverRepository(),
      );
      await tester.pumpWidget(
        MaterialApp(
          theme: buildVoltStopTheme(),
          home: PhoneAuthScreen(app: app),
        ),
      );
      await tester.enterText(find.byType(TextField), '9876543210');
      await tester.tap(find.text('Request one-time code'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      expect(auth.requestedPhones, ['+919876543210']);
      expect(find.text('Resend code in 60s'), findsOneWidget);
      await tester.pump(const Duration(seconds: 60));
      expect(find.text('Resend code'), findsOneWidget);

      final resendButton = find.widgetWithText(TextButton, 'Resend code');
      await tester.ensureVisible(resendButton);
      await tester.pump();
      await tester.tap(resendButton);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(auth.requestedPhones, ['+919876543210', '+919876543210']);
      expect(
        find.textContaining('Supabase accepted a new code request'),
        findsOneWidget,
      );
      expect(
        find.textContaining('SMS delivery to your device is not confirmed'),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'local fixed OTP drives request, sign-in, profile restore, and logout without network',
    (tester) async {
      final config = File('../../supabase/config.toml').readAsStringSync();
      final section = config.split('[auth.sms.test_otp]').last;
      final mappings = <String, String>{
        for (final match in RegExp(
          r'^\s*"([+0-9]+)"\s*=\s*"([0-9]{6})"\s*$',
          multiLine: true,
        ).allMatches(section))
          match.group(1)!: match.group(2)!,
      };
      final phone = '+919876543210';
      final code = mappings[phone];

      expect(code, '123456', reason: 'Use the repository local Auth mapping.');

      final auth = _FixedOtpAuth(mappings);
      final profileRepository = _ProfileOnlyDriverRepository();
      final app = AppController(
        auth: auth,
        driverRepository: profileRepository,
      );

      await tester.pumpWidget(
        MaterialApp(
          theme: buildVoltStopTheme(),
          home: PhoneAuthScreen(app: app),
        ),
      );
      await tester.enterText(find.byType(TextField), phone.substring(3));
      await tester.tap(find.text('Request one-time code'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      expect(auth.requestedPhones, [phone]);
      expect(find.text('Request accepted'), findsOneWidget);
      expect(find.text('OTP sent'), findsNothing);
      expect(
        find.textContaining('SMS delivery to your device is not confirmed'),
        findsOneWidget,
      );

      await tester.enterText(
        find.descendant(
          of: find.byType(OtpScreen),
          matching: find.byType(TextField),
        ),
        code!,
      );
      await tester.tap(find.text('Verify and continue'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      expect(auth.currentSession, isNotNull);
      expect(profileRepository.profileReads, 1);
      expect(app.profileComplete, isTrue);
      expect(find.byType(DriverShell), findsOneWidget);

      final sliderFinder = find.byType(Slider).first;
      final initialSlider = tester.widget<Slider>(sliderFinder);
      initialSlider.onChanged!(initialSlider.min + 10);
      await tester.pump(const Duration(milliseconds: 200));
      final updatedSlider = tester.widget<Slider>(sliderFinder);
      updatedSlider.onChanged!(updatedSlider.max - 10);
      await tester.pump(const Duration(milliseconds: 349));
      expect(profileRepository.routePlanCalls, 0);
      await tester.pump(const Duration(milliseconds: 1));
      expect(profileRepository.routePlanCalls, 1);

      // A new controller/auth repository reads the fake persisted session, which
      // exercises app restoration logic without calling Supabase or SMS.
      final restoredAuth = _FixedOtpAuth(mappings);
      final restoredProfiles = _ProfileOnlyDriverRepository();
      final restoredApp = AppController(
        auth: restoredAuth,
        driverRepository: restoredProfiles,
      );
      await tester.pumpWidget(VoltStopApp(app: restoredApp));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      expect(restoredApp.isSignedIn, isTrue);
      expect(restoredProfiles.profileReads, 1);
      expect(find.byType(DriverShell), findsOneWidget);

      await tester.tap(find.text('Profile'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      await tester.tap(find.text('Sign out'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      expect(restoredAuth.currentSession, isNull);
      expect(_FixedOtpAuth.persistedSession, isNull);
      expect(find.byType(OnboardingScreen), findsOneWidget);
    },
  );
}

class _FixedOtpAuth extends AuthRepository {
  _FixedOtpAuth(this._mappings, {this.sendError});

  static Session? persistedSession;
  final Map<String, String> _mappings;
  final Object? sendError;
  final List<String> requestedPhones = [];

  @override
  Session? get currentSession => persistedSession;

  @override
  Future<void> sendOtp(String phone) async {
    requestedPhones.add(phone);
    if (sendError != null) throw sendError!;
    if (!_mappings.containsKey(phone)) {
      throw StateError('No local fixed OTP mapping for this phone.');
    }
  }

  @override
  Future<void> verifyOtp(String phone, String token) async {
    if (_mappings[phone] != token) {
      throw const AuthException('Invalid test OTP.');
    }
    persistedSession = Session(
      accessToken: 'local-fixed-otp-test-session',
      tokenType: 'bearer',
      user: User.fromJson({
        'id': 'local-fixed-otp-user',
        'app_metadata': <String, dynamic>{},
        'aud': 'authenticated',
        'created_at': '2026-01-01T00:00:00Z',
      })!,
    );
  }

  @override
  Future<void> signOut() async {
    persistedSession = null;
  }
}

class _ProfileOnlyDriverRepository extends DriverRepository {
  _ProfileOnlyDriverRepository()
      : super(ApiClient(accessToken: () async => null));

  int profileReads = 0;
  int routePlanCalls = 0;

  @override
  Future<List<Pitstop>> nearbyPitstops({
    double lat = 17.0,
    double lng = 81.8,
    double radiusKm = 200,
  }) async =>
      [];

  @override
  Future<List<Booking>> bookings() async => [];

  @override
  Future<List<Map<String, dynamic>>> hotelReservations() async => [];

  @override
  Future<Map<String, dynamic>> planRoute({
    required String origin,
    required String destination,
    required double batteryKwh,
    required double stateOfCharge,
    required double efficiency,
    bool persist = true,
    DateTime? departureAt,
  }) async {
    routePlanCalls++;
    return <String, dynamic>{};
  }

  @override
  Future<List<DriverVehicle>> vehicles() async => const [];

  @override
  Future<DriverProfile> profile() async {
    profileReads++;
    return const DriverProfile(
      name: 'Local Test Driver',
      carModel: 'Tata Nexon EV',
      batteryKwh: 40,
      efficiencyKmPerKwh: 6,
    );
  }
}
