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
}
