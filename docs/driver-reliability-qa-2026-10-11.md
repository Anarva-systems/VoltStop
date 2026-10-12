# VoltStop Driver Reliability QA — 2026-10-11

## Executive summary

**PASS:** Flutter analysis, the complete widget/unit suite, the app-side fixed-OTP flow harness, the Realtime refresh widget test, route-preview debounce counting, and debug APK compilation.

**BLOCKED:** Applying or executing the Supabase migrations, testing against a real Supabase Auth/GoTrue service, validating server-side Realtime publication/RLS live, and confirming the driver UI's native first frame on the Android emulator. No Docker was used, no hosted Supabase settings were changed, and no SMS was requested or sent.

The debug APK installed and Android resolved its launcher. On the software-rendered AVD, the app showed the Android/Flutter native splash rather than VoltStop onboarding; the app process was later absent and the launcher was foreground. The screenshot is retained as evidence below. This does **not** establish that the app UI passed native visual QA.

## Verification matrix

| Area | Status | Evidence and limits |
|---|---|---|
| Dart/Flutter static analysis | **PASS** | `flutter analyze lib test` — `No issues found!` (167.8 s). A separate `dart analyze test/local_fixed_otp_flow_test.dart` also reported no issues. |
| Automated tests | **PASS** | Full `flutter test`: **12 tests passed**. Coverage includes model/energy logic, phone-size UI, onboarding/auth/profile recovery, a booking-history Realtime refresh, and the local OTP flow. |
| Fixed OTP mapping — app-level flow | **PASS (harness only)** | `test/local_fixed_otp_flow_test.dart` reads the fixed test mapping `+919876543210 → 123456` from `supabase/config.toml`; a local fake exercises code request, code verification, profile loading, a new controller reading the fake persisted session, profile navigation, and logout. The provider-rejection case checks that the UI does not claim SMS delivery. No network call or SMS is made by this test. |
| Supabase Auth / actual session persistence | **BLOCKED** | No local GoTrue/Auth service was available at `127.0.0.1:54321`; Docker was intentionally not used. The test uses an in-memory fake session, not Supabase SDK secure-storage/session recovery. No real OTP request was made. |
| Realtime client path | **PASS (widget/source)** | `DriverRepository` exposes owner-filtered booking-change streams and catalog notifications; booking history, details, slot selection, and payment status use event-triggered refresh with recovery refreshes. The booking-history widget test updates on a stream event. |
| Realtime server/publication/RLS behavior | **BLOCKED** | The additive publication migration was reviewed but not applied. No live database or server event was available, so publication membership, deployed RLS, event delivery, and cross-user isolation remain unverified. |
| Route slider debounce | **PASS (deterministic test)** | The local Home test changes the battery slider twice 200 ms apart, observes zero route calls at 349 ms after the second change, then exactly one call at 350 ms. The count is from a fake repository; no real network/battery measurement was performed. |
| Route-input hardening | **PASS (source review)** | Client and SQL paths validate bounded LineString GeoJSON, payload size, point count, finite numeric coordinates, and geographic coordinate ranges. Database enforcement remains unexecuted. |
| Data-path/security boundaries | **PASS (source review)** | Driver-owned profile/route/history reads use Supabase paths. Booking history and payment metadata are read-only client queries. Slot holds, booking creation, payment verification, cancellation/refund-sensitive work remain on the trusted API/server path; `cancelBooking` calls `/bookings/{id}/cancel`. No client-side payment/refund write was introduced. |
| Migration/schema verification | **BLOCKED** | `202610100001_supabase_driver_data.sql`, `202610110001_driver_realtime.sql`, and `supabase/verify.sql` received static review only. They were not executed; Docker was not used. |
| Debug APK build | **PASS** | `flutter build apk --debug` succeeded. APK: `apps/mobile/build/app/outputs/flutter-apk/app-debug.apk`, 215,118,522 bytes. ADB non-streaming install succeeded; Package Manager reported `com.voltstop.app/.MainActivity`. |
| Release APK build | **BLOCKED** | `flutter build apk --release` remained in `assembleRelease` without emitting an APK for about nine minutes and was stopped so the lighter debug build could be used for QA. Gradle/AGP/Kotlin emitted upcoming compatibility warnings; no release-build failure diagnostic was captured. |
| Android cold start / display size | **PARTIAL / BLOCKED** | AVD `Medium_Phone` booted with `sys.boot_completed=1`, physical `1080×2400`, density 420. The hardware-rendered emulator went offline and logged an OpenGL `glReadPixels` error (`0x506`). A non-wiping software-rendered restart booted and accepted the APK, but app startup did not reach a verified VoltStop first frame. |
| Native UI/System UI visual gate | **BLOCKED** | The app activity initially started, but the capture remained on the Android/Flutter native splash (not the app's onboarding); the app PID later disappeared and Android's launcher was foreground. Filtered logs had no captured `FATAL EXCEPTION`/ANR record, but showed skipped frames/slow dispatch in the emulator. Status/navigation bars therefore could not be verified against the app's ivory/dark-icon theme in this run. |
| Hosted settings and SMS | **PASS (scope respected)** | No hosted Auth/SMS settings were changed, no migration was applied to hosted Supabase, and no SMS/OTP delivery was attempted. |

### Native capture

The saved **1080×2400** frame is a splash-state capture, not an onboarding screenshot. It is included to make the emulator blocker explicit.

![Android/Flutter splash remained visible instead of VoltStop onboarding](../.work/previews/voltstop-onboarding-coldstart.png)

## Remaining steps

1. **Complete native launch QA on a stable device.** Use a physical Android device or an AVD with adequate host memory (the emulator warned that 7,877 MiB was available versus its 16 GiB recommendation). With the AVD connected, run `flutter run -d emulator-5554 --verbose` and capture the Dart startup output; confirm it reaches VoltStop onboarding, then inspect phone entry and system bars. Do not tap the OTP request button during this check.
2. **Verify real fixed-OTP Auth without SMS.** Provide/reuse a non-Docker local Auth/GoTrue + PostgreSQL endpoint configured from the existing `supabase/config.toml` test mapping. Point the emulator to that local endpoint (typically host-loopback `10.0.2.2` from the AVD) and use its local public/anon key. Exercise the actual Supabase SDK OTP verification and disk-backed session restoration. Keep the test mapping local; do not copy it to hosted production Auth.
3. **Execute migrations only in an approved disposable test database.** Once such a PostgreSQL endpoint is available and authorized, apply the baseline schema if needed, then the additive driver-data and Realtime migrations in timestamp order, and run `supabase/verify.sql` with `ON_ERROR_STOP`. Do not apply these unverified migrations to hosted/production Supabase without explicit approval.
4. **Run a live Realtime/RLS integration check.** After the approved test migration, verify booking status and catalog events arrive for the intended driver, and verify a second user cannot observe another driver's booking event. Confirm the publication and policies with the existing verifier.
5. **Measure real request traffic.** The debounce test proves one fake `planRoute` invocation for rapid slider changes; capture actual request counts/timing on a reachable test backend before making production performance claims.
6. **Optional toolchain maintenance.** Address Flutter's upcoming compatibility warnings by updating Gradle 8.14.3, Android Gradle Plugin 8.11.1, and Kotlin 2.2.20 to versions compatible with the project's Flutter channel, then rebuild release APK after confirming compatible plugin constraints.

## Commands/results recorded

```text
flutter analyze lib test
No issues found! (ran in 167.8s)

flutter test
00:30 +12: All tests passed!

flutter build apk --debug
Built build\app\outputs\flutter-apk\app-debug.apk

adb install --no-streaming -r app-debug.apk
Success

ADB / Android
sys.boot_completed=1
Physical size: 1080x2400
Physical density: 420
Package: com.voltstop.app
Resolved activity: com.voltstop.app/.MainActivity
```


## Exact test-only commands (not executed)

Run these only after an approved, disposable non-Docker PostgreSQL/Auth test endpoint is available. Set `$env:DATABASE_URL` locally; do not put credentials into this report or source control. Skip the baseline migration only if that test database already has the baseline schema.

```powershell
# From D:\voltstop, against an approved disposable test database only:
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f .\supabase\migrations\202610020001_initial_schema.sql
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f .\supabase\migrations\202610100001_supabase_driver_data.sql
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f .\supabase\migrations\202610110001_driver_realtime.sql
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f .\supabase\verify.sql

# Against a non-Docker local Auth endpoint whose config uses the fixed test mapping;
# set $localPublishableKey from that local service's public/anon key, not a service-role key.
$localPublishableKey = '<local-test-publishable-key>'
D:\tools\flutter\bin\flutter.bat run -d emulator-5554 --verbose `
  --dart-define="SUPABASE_URL=http://10.0.2.2:54321" `
  --dart-define="SUPABASE_PUBLISHABLE_KEY=$localPublishableKey"
```

The commands above are a checklist only. No database command, local Auth server, hosted configuration change, or SMS action was performed in this QA run.
