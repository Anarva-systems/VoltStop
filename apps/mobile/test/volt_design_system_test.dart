import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voltstop_mobile/core/theme/app_theme.dart';
import 'package:voltstop_mobile/core/widgets/volt_widgets.dart';

void main() {
  setUp(() => TestWidgetsFlutterBinding.ensureInitialized());

  testWidgets('shared components survive a narrow phone viewport',
      (tester) async {
    tester.view.physicalSize = const Size(320 * 3, 844 * 3);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    const longText =
        'Andhra Pradesh Electric Vehicle Corridor Reservation Reference Number';

    await tester.pumpWidget(MaterialApp(
      theme: buildVoltStopTheme(),
      home: Scaffold(
        body: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const VoltPageHeading(
                eyebrow: 'RESERVATIONS',
                title: longText,
                subtitle: longText,
                trailing: VoltStatusPill(status: 'webhook_verified'),
              ),
              VoltCard(
                child: Row(
                  children: [
                    const Expanded(
                      child: Text(
                        longText,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const VoltStatusPill(status: 'pending', compact: true),
                    VoltButton(
                        label: 'Accept', onPressed: () {}, expand: false),
                  ],
                ),
              ),
              const VoltInlineError(message: longText),
              VoltEmptyState(
                icon: Icons.event_busy_outlined,
                title: longText,
                description: longText,
                action: VoltButton(label: 'Retry', onPressed: () {}),
              ),
            ],
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });

  testWidgets('shared components stay upright at 3x text scale',
      (tester) async {
    tester.view.physicalSize = const Size(390 * 3, 844 * 3);
    tester.view.devicePixelRatio = 3;
    tester.view.padding = const FakeViewPadding(top: 44 * 3, bottom: 34 * 3);
    addTearDown(tester.view.reset);

    final mediaQueryValue = MediaQueryData.fromView(tester.view).copyWith(
      textScaler: const TextScaler.linear(1.6),
      padding: const EdgeInsets.only(top: 44, bottom: 34),
      viewPadding: const EdgeInsets.only(top: 44, bottom: 34),
    );

    await tester.pumpWidget(MaterialApp(
      theme: buildVoltStopTheme(),
      home: MediaQuery(
        data: mediaQueryValue,
        child: Scaffold(
          body: ListView(
            padding: const EdgeInsets.all(16),
            children: const [
              VoltPageHeading(
                eyebrow: 'GARAGE',
                title: 'Saved vehicles',
                subtitle: 'Battery estimates use this vehicle efficiency.',
              ),
              VoltCard(
                child: Row(
                  children: [
                    VoltIconBadge(icon: Icons.electric_car, size: 38),
                    Expanded(
                      child: Text('Tata Nexon EV Max 2024 long edition name'),
                    ),
                    VoltStatusPill(status: 'default'),
                  ],
                ),
              ),
              VoltEmptyState(
                icon: Icons.local_fire_department_outlined,
                title: 'No restaurants on this corridor yet',
                description: 'Try widening your search along the highway.',
              ),
            ],
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });
}
