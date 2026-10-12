import 'package:supabase_flutter/supabase_flutter.dart';
import '../core/config/app_config.dart';

class AuthRepository {
  AuthRepository({SupabaseClient? client}) : _client = client;

  final SupabaseClient? _client;

  bool get isConfigured => AppConfig.hasSupabase && _client != null;
  Session? get currentSession => _client?.auth.currentSession;
  User? get currentUser => _client?.auth.currentUser;

  Future<void> sendOtp(String phone) async {
    final client = _client;
    if (client == null) {
      throw const AuthException(
          'Phone sign-in needs SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY configuration.');
    }
    await client.auth.signInWithOtp(phone: phone);
  }

  Future<void> verifyOtp(String phone, String token) async {
    final client = _client;
    if (client == null)
      throw const AuthException('Supabase authentication is not configured.');
    await client.auth.verifyOTP(phone: phone, token: token, type: OtpType.sms);
  }

  Future<void> signOut() async {
    final client = _client;
    if (client == null) return;
    await client.auth.signOut();
  }

  Stream<AuthState> get authChanges =>
      _client?.auth.onAuthStateChange ?? const Stream<AuthState>.empty();
}
