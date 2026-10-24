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

void main() {
  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
  });

  testWidgets('onboarding fits a phone viewport and opens phone sign-in', (
    tester,
  ) async {
    _setPhoneViewport(tester);
    final app = _newApp();

    await tester.pumpWidget(
      MaterialApp(
        theme: buildVoltStopTheme(),
        home: OnboardingScreen(app: app),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Your next stop,\nwell chosen.'), findsOneWidget);
    expect(find.text('Srikakulam'), findsOneWidget);
    expect(find.text('Vijayawada'), findsOneWidget);
    expect(find.text('Continue with phone'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await expectLater(
      find.byType(OnboardingScreen),
      matchesGoldenFile('goldens/onboarding_phone_390x844.png'),
    );

    await tester.tap(find.text('Continue with phone'));
    await tester.pumpAndSettle();
    expect(find.text('DRIVER ACCESS'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
  });

  testWidgets('profile setup rejects efficiency above the API limit locally',
      (tester) async {
    _setPhoneViewport(tester);
    final repository = _RecordingProfileSaveRepository();
    final app = AppController(
      auth: AuthRepository(),
      driverRepository: repository,
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: buildVoltStopTheme(),
        home: ProfileSetupScreen(app: app),
      ),
    );
    await tester.pumpAndSettle();
    final fields = find.byType(TextField);
    await tester.enterText(fields.at(0), 'Ashapu Lokesh');
    await tester.enterText(fields.at(1), 'Tata');
    await tester.enterText(fields.at(2), 'Sierra');
    await tester.enterText(fields.at(3), '50');
    await tester.enterText(fields.at(4), '120');
    await tester.tap(find.text('Complete setup'));
    await tester.pumpAndSettle();

    expect(
      find.text(
        'Efficiency must be 20 km/kWh or less. Enter efficiency per kWh, not total driving range.',
      ),
      findsOneWidget,
    );
    expect(repository.saveCalls, 0);
  });
  testWidgets(
    'OTP rejects malformed codes locally and recovers after profile read failure',
    (tester) async {
      _setPhoneViewport(tester);
      final auth = _RecordingAuthRepository();
      final repository = _PreviewDriverRepository()..failProfile = true;
      final app = AppController(auth: auth, driverRepository: repository);

      await tester.pumpWidget(
        MaterialApp(
          theme: buildVoltStopTheme(),
          home: OtpScreen(app: app, phone: '+919876543210'),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Verify and continue'));
      await tester.pumpAndSettle();
      expect(
        find.text('Enter the six-digit verification code.'),
        findsOneWidget,
      );
      expect(auth.verifyCalls, 0);

      await tester.enterText(find.byType(TextField), '123456');
      await tester.tap(find.text('Verify and continue'));
      await tester.pumpAndSettle();
      expect(auth.verifyCalls, 1);
      expect(app.isSignedIn, isTrue);
      expect(find.byType(ProfileSetupScreen), findsNothing);
      expect(
        find.textContaining(
          'Your code was verified, but VoltStop could not load your driver profile',
        ),
        findsOneWidget,
      );
      expect(find.text('Retry profile loading'), findsOneWidget);

      repository.failProfile = false;
      await tester.tap(find.text('Retry profile loading'));
      await tester.pumpAndSettle();
      expect(find.byType(ProfileSetupScreen), findsOneWidget);
    },
  );

  testWidgets('backend outage does not request or consume an OTP',
      (tester) async {
    _setPhoneViewport(tester);
    final auth = _OtpRequestRecordingAuthRepository();
    final repository = _PreviewDriverRepository()..failReadiness = true;
    final app = AppController(auth: auth, driverRepository: repository);

    await tester.pumpWidget(
      MaterialApp(
        theme: buildVoltStopTheme(),
        home: PhoneAuthScreen(app: app),
      ),
    );
    await tester.enterText(find.byType(TextField), '9876543210');
    await tester.tap(find.text('Request one-time code'));
    await tester.pumpAndSettle();

    expect(auth.sendCalls, 0);
    expect(
      find.textContaining('no sign-in code was requested'),
      findsOneWidget,
    );
  });

  testWidgets('driver home prioritizes route planning at phone dimensions', (
    tester,
  ) async {
    _setPhoneViewport(tester);
    final app = _newApp()
      ..profile = const DriverProfile(
        name: 'Maya Rao',
        carModel: 'Tata Nexon EV',
        batteryKwh: 40,
        efficiencyKmPerKwh: 6,
        currentSoc: 75,
      );

    await tester.pumpWidget(
      MaterialApp(
        theme: buildVoltStopTheme(),
        home: DriverShell(
          app: app,
          clock: () => DateTime(2026, 10, 23, 9, 0),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Where to next, Maya?'), findsOneWidget);
    expect(find.text('PLAN A CHARGE-READY ROUTE'), findsOneWidget);
    expect(find.text('Current battery charge'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await expectLater(
      find.byType(Scaffold).first,
      matchesGoldenFile('goldens/driver_home_phone_390x844.png'),
    );

    await tester.tap(find.byTooltip('Reverse route'));
    await tester.pumpAndSettle();
    expect(find.text('FROM'), findsOneWidget);
    expect(find.text('Vijayawada'), findsWidgets);
    await tester.scrollUntilVisible(
      find.text('Stops on your route'),
      260,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Stops on your route'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Coastline Charge Hub'),
      260,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Coastline Charge Hub'), findsOneWidget);
  });

  testWidgets('route planner saves a missing charge and retries with the API', (
    tester,
  ) async {
    final app = _newApp()
      ..profile = const DriverProfile(
        id: 'driver-1',
        name: 'Maya Rao',
        carModel: 'Tata Nexon EV',
        batteryKwh: 40,
        efficiencyKmPerKwh: 6,
      );

    await tester.pumpWidget(
      MaterialApp(
        theme: buildVoltStopTheme(),
        home: RoutePlannerScreen(
          app: app,
          origin: 'Srikakulam',
          destination: 'Vijayawada',
          soc: null,
          departureAt: DateTime.now().add(const Duration(hours: 2)),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Set your current battery charge'), findsOneWidget);
    final button = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Save charge & calculate route'),
    );
    expect(button.onPressed, isNull);

    tester.widget<Slider>(find.byType(Slider)).onChanged!(75);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save charge & calculate route'));
    await tester.pumpAndSettle();

    expect(app.profile?.currentSoc, 75);
    expect(
        (app.driverRepository as _PreviewDriverRepository).routePlanCalls, 1);
    await tester.scrollUntilVisible(
      find.text('Estimated drive time'),
      240,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Estimated drive time'), findsOneWidget);
    expect(find.text('3 hr'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

void _setPhoneViewport(WidgetTester tester) {
  final view = tester.view;
  final oldSize = view.physicalSize;
  final oldRatio = view.devicePixelRatio;
  final oldPadding = view.viewPadding;
  addTearDown(() {
    view.physicalSize = oldSize;
    view.devicePixelRatio = oldRatio;
    view.viewPadding = oldPadding;
  });
  view.devicePixelRatio = 1;
  view.physicalSize = const Size(390, 844);
  view.viewPadding = const FakeViewPadding(top: 47, bottom: 34);
}

AppController _newApp() => AppController(
      auth: AuthRepository(),
      driverRepository: _PreviewDriverRepository(),
    );

class _RecordingAuthRepository extends AuthRepository {
  int verifyCalls = 0;
  Session? session;

  @override
  Session? get currentSession => session;

  @override
  Future<void> verifyOtp(String phone, String token) async {
    verifyCalls++;
    session = Session(
      accessToken: 'widget-test-access-token',
      tokenType: 'bearer',
      user: User.fromJson({
        'id': 'widget-test-user',
        'app_metadata': <String, dynamic>{},
        'aud': 'authenticated',
        'created_at': '2026-01-01T00:00:00Z',
      })!,
    );
  }
}

class _OtpRequestRecordingAuthRepository extends _RecordingAuthRepository {
  int sendCalls = 0;

  @override
  Future<void> sendOtp(String phone) async {
    sendCalls++;
  }
}

class _RecordingProfileSaveRepository extends _PreviewDriverRepository {
  int saveCalls = 0;

  @override
  Future<DriverProfile> saveProfile(DriverProfile profile) async {
    saveCalls++;
    return profile;
  }
}

class _PreviewDriverRepository extends DriverRepository {
  _PreviewDriverRepository() : super(ApiClient(accessToken: () async => null));

  bool failProfile = false;
  bool failReadiness = false;
  int routePlanCalls = 0;

  @override
  Future<void> checkApiReadiness() async {
    if (failReadiness) {
      throw const ApiException(
        'VoltStop services are not ready. Try again shortly.',
        statusCode: 503,
        code: 'DEPENDENCIES_UNAVAILABLE',
        category: 'readiness',
      );
    }
  }

  @override
  Future<List<DriverVehicle>> vehicles() async => const [];

  @override
  Future<DriverProfile> profile() async {
    if (failProfile) throw StateError('temporary profile read failure');
    return const DriverProfile();
  }

  @override
  Future<DriverProfile> saveProfile(DriverProfile profile) async => profile;

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
    return {
      'origin': origin,
      'destination': destination,
      'distance_km': 447.34,
      'estimated_duration_seconds': 10800,
      'estimated_consumption_kwh': 74.56,
      'estimated_remaining_soc': stateOfCharge - 186.4,
      'recommended_pitstops': <dynamic>[
        {
          'vendor': {
            'id': 'nh16-coastline',
            'name': 'Coastline Charge Hub',
            'type': 'charging',
            'address': 'Tuni, Andhra Pradesh',
          },
          'distance_km': 18.4,
        },
      ],
    };
  }

  @override
  Future<List<Pitstop>> nearbyPitstops({
    double lat = 17.0,
    double lng = 81.8,
    double radiusKm = 200,
  }) async =>
      const [
        Pitstop(
          id: 'nh16-coastline',
          name: 'Coastline Charge Hub',
          type: 'charging',
          address: 'Tuni, Andhra Pradesh',
          distanceKm: 18.4,
          services: [
            {'service_type': 'charging', 'price_inr': 249},
          ],
          slots: [],
          isVerified: true,
        ),
      ];

  @override
  Future<List<Booking>> bookings() async => const [];

  @override
  Future<List<Map<String, dynamic>>> hotelReservations() async => const [];
}
