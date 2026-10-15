import 'package:flutter/foundation.dart';
import '../core/services/api_client.dart';
import '../models/driver_profile.dart';
import '../models/driver_vehicle.dart';
import '../repositories/auth_repository.dart';
import '../repositories/driver_repository.dart';

class AppController extends ChangeNotifier {
  AppController({required this.auth, required this.driverRepository});

  final AuthRepository auth;
  final DriverRepository driverRepository;
  DriverProfile? profile;
  List<DriverVehicle> vehicles = const [];
  String? profileLoadError;
  String? profileLoadErrorCategory;
  String? vehicleLoadError;
  bool isProfileLoading = false;

  DriverVehicle? get activeVehicle {
    for (final vehicle in vehicles) {
      if (vehicle.isDefault) return vehicle;
    }
    return vehicles.isEmpty ? null : vehicles.first;
  }

  bool get isSignedIn => auth.currentSession != null;
  bool get profileComplete =>
      activeVehicle?.isComplete ?? (profile?.isComplete ?? false);

  Future<void> checkApiReadiness() => driverRepository.checkApiReadiness();

  Future<void> loadVehicles({bool notify = true}) async {
    try {
      vehicles = await driverRepository.vehicles();
      vehicleLoadError = null;
    } catch (error) {
      vehicleLoadError = '$error';
    }
    if (notify) notifyListeners();
  }

  Future<void> loadProfile() async {
    if (!isSignedIn) return;
    isProfileLoading = true;
    notifyListeners();
    try {
      profile = await driverRepository.profile();
      profileLoadError = null;
      profileLoadErrorCategory = null;
      await loadVehicles(notify: false);
    } catch (error) {
      profile = null;
      profileLoadError = '$error';
      profileLoadErrorCategory =
          error is ApiException ? error.category : 'unexpected';
    } finally {
      isProfileLoading = false;
      notifyListeners();
    }
  }

  Future<void> saveProfile(DriverProfile value) async {
    profile = await driverRepository.saveProfile(value);
    profileLoadError = null;
    profileLoadErrorCategory = null;
    notifyListeners();
  }

  Future<void> refreshVehicles() => loadVehicles();

  Future<void> logout() async {
    await auth.signOut();
    profile = null;
    vehicles = const [];
    profileLoadError = null;
    profileLoadErrorCategory = null;
    vehicleLoadError = null;
    notifyListeners();
  }
}
