class AppConfig {
  const AppConfig._();

  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000/api/v1',
  );
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

  static bool get hasSupabase =>
      supabaseUrl.isNotEmpty && supabasePublishableKey.isNotEmpty;
  static bool get hasMaps => osmTileUrl.isNotEmpty;
  static bool get hasGoogleMaps => false;
}
