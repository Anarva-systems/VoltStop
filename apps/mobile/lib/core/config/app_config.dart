class AppConfig {
  const AppConfig._();

  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000/api/v1',
  );
  static const hasExplicitApiBaseUrl = bool.hasEnvironment('API_BASE_URL');
  static const hasExplicitSupabaseUrl = bool.hasEnvironment('SUPABASE_URL');
  static const hasExplicitSupabaseKey =
      bool.hasEnvironment('SUPABASE_PUBLISHABLE_KEY') ||
          bool.hasEnvironment('SUPABASE_ANON_KEY');
  static const discoveryFallbackLat = 18.2969;
  static const discoveryFallbackLng = 83.8968;
  static const appEnvironment = String.fromEnvironment(
    'APP_ENV',
    defaultValue: 'development',
  );
  static const supabaseUrl = String.fromEnvironment(
    'SUPABASE_URL',
    defaultValue: 'https://zbofzjnjgyfuistzomtt.supabase.co',
  );
  // Client-safe Supabase publishable key; never place a service-role key here.
  static const supabasePublishableKey = String.fromEnvironment(
    'SUPABASE_PUBLISHABLE_KEY',
    defaultValue: String.fromEnvironment(
      'SUPABASE_ANON_KEY',
      defaultValue: 'sb_publishable_bYnuroDBhp5o4R9KmgmYOg_lIYVEfVn',
    ),
  );
  static const supabaseAnonKey = supabasePublishableKey;
  static const osrmRouterUrl = String.fromEnvironment(
    'OSRM_ROUTER_URL',
    defaultValue: 'https://router.project-osrm.org/route/v1/driving',
  );
  static const osmTileUrl = String.fromEnvironment(
    'OSM_TILE_URL',
    defaultValue: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  );

  static String? validateApiBaseUrl(String value,
      {required String environment}) {
    final uri = Uri.tryParse(value);
    if (uri == null ||
        !uri.hasScheme ||
        !uri.hasAuthority ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.query.isNotEmpty ||
        uri.fragment.isNotEmpty) {
      return 'API_BASE_URL must be an absolute service URL.';
    }
    if ({'staging', 'production'}.contains(environment.toLowerCase())) {
      final host = uri.host.toLowerCase();
      final localHost = host == 'localhost' ||
          host.endsWith('.local') ||
          host.contains(':') ||
          RegExp(r'^\d{1,3}(?:\.\d{1,3}){3}$').hasMatch(host);
      if (uri.scheme != 'https' || localHost) {
        return 'Staging and production API_BASE_URL values must use HTTPS with a DNS host.';
      }
    }
    return null;
  }

  static String? get apiConfigurationError => validateBuildConfiguration(
        apiBaseUrl,
        environment: appEnvironment,
        isRelease: const bool.fromEnvironment('dart.vm.product'),
        hasExplicitApiBaseUrl: hasExplicitApiBaseUrl,
        hasExplicitSupabaseUrl: hasExplicitSupabaseUrl,
        hasExplicitSupabaseKey: hasExplicitSupabaseKey,
      );

  static String? validateBuildConfiguration(
    String value, {
    required String environment,
    required bool isRelease,
    required bool hasExplicitApiBaseUrl,
    required bool hasExplicitSupabaseUrl,
    required bool hasExplicitSupabaseKey,
  }) {
    final productionBuild =
        isRelease || environment.toLowerCase() == 'production';
    if (productionBuild && !hasExplicitApiBaseUrl) {
      return 'Release builds must set API_BASE_URL to the production API.';
    }
    if (productionBuild && !hasExplicitSupabaseUrl) {
      return 'Release builds must set SUPABASE_URL to the production authentication project.';
    }
    if (productionBuild && !hasExplicitSupabaseKey) {
      return 'Release builds must set the production SUPABASE_PUBLISHABLE_KEY.';
    }
    return validateApiBaseUrl(
      value,
      environment: productionBuild ? 'production' : environment,
    );
  }

  static bool get hasSupabase =>
      supabaseUrl.isNotEmpty && supabasePublishableKey.isNotEmpty;
  static bool get hasMaps => osmTileUrl.isNotEmpty;
  static bool get hasGoogleMaps => false;
}
