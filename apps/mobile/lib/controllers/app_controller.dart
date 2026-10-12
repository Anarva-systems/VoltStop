import 'package:flutter/foundation.dart';
import '../models/driver_profile.dart';
import '../repositories/auth_repository.dart';
import '../repositories/driver_repository.dart';

class AppController extends ChangeNotifier {
  AppController({required this.auth, required this.driverRepository});

  final AuthRepository auth;
  final DriverRepository driverRepository;
  DriverProfile? profile;
  String? profileLoadError;
  bool isProfileLoading = false;

  bool get isSignedIn => auth.currentSession != null;
  bool get profileComplete => profile?.isComplete ?? false;

  Future<void> loadProfile() async {
    if (!isSignedIn) return;
    isProfileLoading = true;
    notifyListeners();
    try {
      profile = await driverRepository.profile();
      profileLoadError = null;
    } catch (error) {
      profile = null;
      profileLoadError = '$error';
    } finally {
      isProfileLoading = false;
      notifyListeners();
    }
  }

  Future<void> saveProfile(DriverProfile value) async {
    profile = await driverRepository.saveProfile(value);
    profileLoadError = null;
    notifyListeners();
  }

  Future<void> logout() async {
    await auth.signOut();
    profile = null;
    profileLoadError = null;
    notifyListeners();
  }
}
