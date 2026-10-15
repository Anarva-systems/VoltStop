import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'controllers/app_controller.dart';
import 'core/config/app_config.dart';
import 'core/services/api_client.dart';
import 'core/theme/app_theme.dart';
import 'core/widgets/volt_widgets.dart';
import 'features/auth/views/auth_screens.dart';
import 'features/driver/views/driver_screens.dart';
import 'repositories/auth_repository.dart';
import 'repositories/driver_repository.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(voltSystemUiOverlayStyle);
  final apiConfigError = AppConfig.apiConfigurationError;
  if (apiConfigError != null) {
    runApp(_ApiConfigurationError(message: apiConfigError));
    return;
  }
  if (AppConfig.hasSupabase) {
    await Supabase.initialize(
      url: AppConfig.supabaseUrl,
      publishableKey: AppConfig.supabasePublishableKey,
    );
  }
  final supabaseClient =
      AppConfig.hasSupabase ? Supabase.instance.client : null;
  final auth = AuthRepository(client: supabaseClient);
  final api =
      ApiClient(accessToken: () async => auth.currentSession?.accessToken);
  final app = AppController(
    auth: auth,
    driverRepository: DriverRepository(api, supabase: supabaseClient),
  );
  runApp(VoltStopApp(app: app));
}

class VoltStopApp extends StatelessWidget {
  const VoltStopApp({super.key, required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'VoltStop',
        debugShowCheckedModeBanner: false,
        theme: buildVoltStopTheme(),
        home: _Gate(app: app),
      );
}

class _Gate extends StatefulWidget {
  const _Gate({required this.app});
  final AppController app;
  @override
  State<_Gate> createState() => _GateState();
}

class _GateState extends State<_Gate> {
  bool _ready = false;

  @override
  void initState() {
    super.initState();
    _restore();
  }

  Future<void> _restore() async {
    if (widget.app.isSignedIn) await widget.app.loadProfile();
    if (mounted) setState(() => _ready = true);
  }

  @override
  Widget build(BuildContext context) {
    if (!_ready) return const SplashScreen();
    if (!widget.app.isSignedIn) return OnboardingScreen(app: widget.app);
    if (widget.app.profileLoadError != null) {
      return _ProfileRecoveryScreen(app: widget.app, onRetry: _restore);
    }
    if (!widget.app.profileComplete) return ProfileSetupScreen(app: widget.app);
    return DriverShell(app: widget.app);
  }
}

class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(
          child: Center(
            child: Column(mainAxisSize: MainAxisSize.min, children: const [
              BrandMark(),
              SizedBox(height: 18),
              CircularProgressIndicator(color: VoltColors.green),
              SizedBox(height: 12),
              Text('Getting your next stop ready',
                  style: TextStyle(color: VoltColors.muted)),
            ]),
          ),
        ),
      );
}

class _ProfileRecoveryScreen extends StatelessWidget {
  const _ProfileRecoveryScreen({required this.app, required this.onRetry});
  final AppController app;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(
            child: Center(
                child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: VoltCard(
                        child:
                            Column(mainAxisSize: MainAxisSize.min, children: [
                      const Icon(Icons.cloud_off_outlined,
                          color: VoltColors.warning, size: 42),
                      const SizedBox(height: 12),
                      const Text('We could not load your driver profile.',
                          textAlign: TextAlign.center),
                      const SizedBox(height: 6),
                      Text(_profileIssueLabel(app.profileLoadErrorCategory),
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                              color: VoltColors.warning,
                              fontWeight: FontWeight.w700)),
                      const SizedBox(height: 8),
                      Text('${app.profileLoadError}',
                          textAlign: TextAlign.center,
                          style: const TextStyle(color: VoltColors.muted)),
                      const SizedBox(height: 16),
                      FilledButton.icon(
                          onPressed: onRetry,
                          icon: const Icon(Icons.refresh),
                          label: const Text('Retry')),
                      TextButton(
                          onPressed: () async {
                            await app.logout();
                            if (context.mounted)
                              Navigator.of(context).pushAndRemoveUntil(
                                  MaterialPageRoute(
                                      builder: (_) =>
                                          OnboardingScreen(app: app)),
                                  (_) => false);
                          },
                          child: const Text('Sign out')),
                    ]))))),
      );
}

class _ApiConfigurationError extends StatelessWidget {
  const _ApiConfigurationError({required this.message});
  final String message;
  @override
  Widget build(BuildContext context) => MaterialApp(
        home: Scaffold(
            body: SafeArea(
                child: Center(
                    child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
              'VoltStop is not configured for secure service access. $message',
              textAlign: TextAlign.center),
        )))),
      );
}

String _profileIssueLabel(String? category) => switch (category) {
      'authentication' => 'Sign-in session issue',
      'authorization' => 'Account access issue',
      'deployment_unavailable' => 'API deployment missing',
      'not_found' => 'Profile not found',
      'server' => 'VoltStop service issue',
      'timeout' => 'Request timed out',
      'tls' => 'Secure connection issue',
      'network' => 'Network connection issue',
      'dns' => 'DNS lookup issue',
      'response' => 'Unexpected API response',
      _ => 'Profile loading issue',
    };
