# VoltStop driver app — Supabase and emulator verification

**Review date:** 2026-10-10  
**Scope:** Existing Flutter driver application, additive driver-data migration, trusted booking/payment/refund boundaries, and safe OTP-screen QA.

## Status summary

| Item | Status | Evidence / limitation |
|---|---|---|
| Additive migration structure, relationships, indexes, grants, and RLS | **PASS — static review** | `202610100001_supabase_driver_data.sql` was reviewed with the existing base migrations. Owner-scoped `routes` references `profiles(id)` with cascade delete; `routes_user_created_idx` supports a driver's newest-first history; route insert grants exclude `user_id` and the row policy binds ownership to `auth.uid()`. The historical-vendor helper is `SECURITY DEFINER`, has an empty `search_path`, is auth-bound, and returns only a boolean. `route_pitstops` is `SECURITY INVOKER`, limits radius/results, and has execute revoked from `PUBLIC`/`anon` and granted to `authenticated`. |
| Applying/executing the migration against PostgreSQL | **BLOCKED** | `supabase status` reports “Not linked” and cannot reach the Docker Desktop Linux engine; `docker info` cannot connect to that engine and `127.0.0.1:54322` is closed. No local PostgreSQL parser is installed. No hosted migration was applied. Static review is not execution proof. |
| Driver data paths | **PASS — source review** | `DriverRepository` reads/upserts the signed-in profile through `profiles`, persists explicit route plans to `routes`, uses the route-pitstop RPC for route recommendations, and reads booking history (including related vendor/payment details) from Supabase. Route geometry/distance is obtained from the configured OSRM endpoint; previews are debounced and the home battery slider does not persist a route on every movement. |
| Booking, slot, payment, and refund trust boundaries | **PASS — source review + API tests** | The mobile app calls the API for slot locks, booking creation/cancellation, and order creation. Razorpay callbacks are not treated as proof of payment: the app polls the booking status, which is server-confirmed by a signed webhook. Refund issuance is in the trusted API service after an approved request; provider timeouts/ambiguous outcomes are held for reconciliation. The mobile repository has no direct refund write. `python -m pytest apps/api/tests -q`: **75 passed, 3 skipped** (one Starlette/httpx deprecation warning). |
| Dart analysis and Flutter tests | **PASS** | `dart analyze lib test`: **No issues found**. Full Flutter suite after the OTP fix: **9 passed**. Tests include phone-size onboarding/home layout, local rejection of malformed OTP without a network call, and recovery when profile loading fails after a mocked authenticated OTP. |
| Android debug build and installation | **PASS** | Debug APK built from the updated source; ADB streamed install returned **Success** on `emulator-5554`. APK SHA-256: `B2D62882ECB56123ACDED19D88866FE1EADD328D201EAC69003DF6D0094E843F`. Build emitted only upcoming compatibility warnings for Gradle 8.14.3, AGP 8.11.1, and Kotlin 2.2.20. |
| Native-screen QA | **PASS with emulator caveat** | Latest installed APK was captured at **1080×2400**: onboarding and phone-entry screen were visually inspected with native Android typography; the phone-entry capture shows dark status icons on the ivory surface and an ivory navigation bar. Android System UI ANR occurred during a cold start; choosing the non-destructive Wait action recovered the app and exposed onboarding. One transient recovery frame showed pale status icons, so repeat on a healthy emulator before release. An OTP-entry screen was also captured on-device before the final logic-only OTP patch; current OTP widget behavior is covered by the passing tests. |
| Live Supabase OTP / successful authentication-state sync | **BLOCKED intentionally** | No hosted provider/settings were inspected or changed, no migration was applied, and no verification code was entered or verified in this review. The emulator displayed an OTP-entry UI at one point; its request history is uncertain, and that UI is not proof of SMS delivery or successful authentication. Real end-to-end auth requires an enabled provider and an authorized test number, or the local test OTP stack below. |

## Migration review details

- `public.routes` is a new driver-owned history table. It has a UUID primary key, `user_id → public.profiles(id) ON DELETE CASCADE`, non-empty origin/destination constraints, pilot-corridor constraint, positive distance/battery/efficiency checks, bounded state-of-charge inputs, and a GeoJSON LineString shape check.
- The index is `(user_id, created_at DESC)`, matching owner-filtered newest-first history reads.
- RLS is enabled. Authenticated users can select/delete their own routes and insert only the explicitly granted route columns. They cannot directly update a route or choose another `user_id`; the default and policy use `auth.uid()`. Anonymous access is revoked.
- Historical vendor/slot visibility is limited to vendors/slots tied to the caller's own booking. The security-definer helper uses an empty search path and reveals only a boolean, not booking rows.
- Route recommendations run as the invoker so existing vendor/service/slot RLS continues to apply. The function checks LineString type, at least two points, and a maximum 50 km radius; it returns only active/verified vendors, orders them along the route, and caps results at 20.
- **Non-blocking hardening opportunity:** add a maximum serialized GeoJSON size and coordinate-range/shape checks on route-history input. The current ownership RLS prevents cross-user writes, but the migration does not impose a per-user route-history quota.

## Safe Phone Auth checklist

### Preferred: local fixed test OTP, no SMS provider call

The repository's `supabase/config.toml` already enables local SMS signup and contains fixed test-OTP mappings for both supported phone-string forms. Supabase's CLI documentation confirms that `auth.sms.test_otp` maps a phone number to a fixed OTP for testing; the mapping is local configuration and does not prove hosted SMS delivery.

1. Start Docker Desktop, then start the local Supabase stack from `D:\voltstop` (`supabase start`). Do not point this at the hosted project.
2. Use a disposable local database. Apply the migration only to that local stack after confirming the migration files, then run `supabase/verify.sql` against the local database and check the route RPC and RLS as anonymous, owner, and different-user roles. Do not run a reset against data that is not disposable/backed up.
3. Restart the local Auth service after config changes so the fixed OTP map is loaded.
4. Build the emulator app with the local API URL and local **publishable/anon** key from `supabase status` (never a service-role key): `--dart-define=SUPABASE_URL=http://10.0.2.2:54321 --dart-define=SUPABASE_PUBLISHABLE_KEY=<local-publishable-key>`.
5. Use one mapped test number and its configured fixed code; verify the returned session, profile read, signed-in gate, and sign-out. The local map should bypass SMS delivery. Confirm with local Auth logs that no external SMS provider was invoked.

### Hosted Phone Auth, only after explicit authorization to send a test SMS

1. In the intended Supabase project, open **Authentication → Sign In / Providers → Phone** and enable phone sign-in.
2. Select a supported SMS provider (for example Twilio/Twilio Verify, MessageBird, Vonage, or TextLocal where available). Enter its account/sender credentials in Supabase's protected provider settings—never in app source, repository files, or chat.
3. Configure an approved sender, OTP message template, expiry, provider delivery, and destination-country requirements. For India, confirm applicable TRAI/DLT sender/template registration before production use.
4. Configure sensible OTP rate limits and CAPTCHA/abuse protection before broad rollout.
5. Use a provider-approved test destination/credentials if supported. Otherwise, send only to an explicitly approved, controlled test handset after permission; verify receipt independently, then enter the six-digit code in the app. Do not infer delivery from the app's “check your messages” screen.
6. Verify the resulting Supabase session and profile-loading state; then sign out and confirm the app returns to the signed-out gate. Do not enable production sending until the provider, template, regional compliance, limits, and monitoring are validated.

## Exact remaining steps

1. **Local database:** make Docker's local engine available; validate the migration on a disposable local Supabase stack and execute `supabase/verify.sql`. Until then, SQL execution remains unverified.
2. **Phone Auth:** choose the local fixed-OTP path first. For hosted SMS, an authorized project operator must configure the provider in the dashboard and approve a test recipient. No hosted provider settings were changed and no code was entered or verified; the OTP screen alone does not establish whether a prior request sent an SMS.
3. **Device QA:** repeat the cold-start capture on a responsive emulator/device (the current AVD intermittently ANRs in Android System UI). Use the local fixed-OTP map for full sign-in/session testing; otherwise keep real OTP submission blocked until a recipient is approved.
4. **Release housekeeping:** update Gradle/AGP/Kotlin to Flutter-supported versions before their upcoming compatibility cutoff; the current build succeeded, but Flutter emitted deprecation warnings.

## Evidence files

- Latest native onboarding: `D:\voltstop\apps\mobile\.work\visual-qa\onboarding_latest_native_recovered.png` (1080×2400; captured after the System UI Wait recovery).
- Latest native phone-entry form: `D:\voltstop\apps\mobile\.work\visual-qa\phone_auth_latest_native.png` (1080×2400; no Send-code tap).
- Native OTP-entry rendering from the prior app build: `D:\voltstop\apps\mobile\.work\visual-qa\phone_auth_native_autonomous.png` (1080×2400; layout remains the same; final OTP logic is additionally tested with fake auth).

## Official references

- [Supabase Phone sign-in](https://supabase.com/docs/guides/auth/phone-login)
- [Supabase CLI config — SMS test OTP](https://supabase.com/docs/guides/local-development/cli/config)
- [Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Supabase database functions](https://supabase.com/docs/guides/database/functions)
