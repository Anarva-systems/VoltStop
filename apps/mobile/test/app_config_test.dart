import 'package:flutter_test/flutter_test.dart';
import 'package:voltstop_mobile/core/config/app_config.dart';

void main() {
  test('development API URLs may use emulator and LAN addresses', () {
    expect(
        AppConfig.validateApiBaseUrl('http://10.0.2.2:8000/api/v1',
            environment: 'development'),
        isNull);
    expect(
        AppConfig.validateApiBaseUrl('http://192.168.1.2:8000/api/v1',
            environment: 'development'),
        isNull);
  });

  test('production API URLs require public HTTPS', () {
    expect(
        AppConfig.validateApiBaseUrl('https://api.voltstop.example/api/v1',
            environment: 'production'),
        isNull);
    expect(
        AppConfig.validateApiBaseUrl('http://api.voltstop.example/api/v1',
            environment: 'production'),
        isNotNull);
    expect(
        AppConfig.validateApiBaseUrl('https://192.168.1.2/api/v1',
            environment: 'production'),
        isNotNull);
  });

  test('release API configuration must be explicit', () {
    expect(
      AppConfig.validateBuildConfiguration(
        'http://10.0.2.2:8000/api/v1',
        environment: 'development',
        isRelease: true,
        hasExplicitApiBaseUrl: false,
        hasExplicitSupabaseUrl: true,
        hasExplicitSupabaseKey: true,
      ),
      contains('Release builds must set API_BASE_URL'),
    );
  });

  test('release API configuration rejects LAN and emulator URLs', () {
    for (final url in [
      'http://10.0.2.2:8000/api/v1',
      'http://192.168.1.4:8000/api/v1',
      'https://192.168.1.4/api/v1',
    ]) {
      expect(
        AppConfig.validateBuildConfiguration(
          url,
          environment: 'development',
          isRelease: true,
          hasExplicitApiBaseUrl: true,
          hasExplicitSupabaseUrl: true,
          hasExplicitSupabaseKey: true,
        ),
        isNotNull,
      );
    }
  });

  test('release accepts the production VoltStop API URL', () {
    expect(
      AppConfig.validateBuildConfiguration(
        'https://api-one-nu-41.vercel.app/api/v1',
        environment: 'development',
        isRelease: true,
        hasExplicitApiBaseUrl: true,
        hasExplicitSupabaseUrl: true,
        hasExplicitSupabaseKey: true,
      ),
      isNull,
    );
  });

  test('release requires explicit Supabase project configuration', () {
    final apiUrl = 'https://api-one-nu-41.vercel.app/api/v1';
    expect(
      AppConfig.validateBuildConfiguration(
        apiUrl,
        environment: 'production',
        isRelease: true,
        hasExplicitApiBaseUrl: true,
        hasExplicitSupabaseUrl: false,
        hasExplicitSupabaseKey: false,
      ),
      contains('SUPABASE_URL'),
    );
    expect(
      AppConfig.validateBuildConfiguration(
        apiUrl,
        environment: 'production',
        isRelease: true,
        hasExplicitApiBaseUrl: true,
        hasExplicitSupabaseUrl: true,
        hasExplicitSupabaseKey: false,
      ),
      contains('SUPABASE_PUBLISHABLE_KEY'),
    );
  });
}
