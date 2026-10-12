# VoltStop OTP Delivery Investigation — 2026-10-11

## What the Flutter client actually knows

`PhoneAuthScreen._send()` normalizes the entered Indian number, then awaits `AuthRepository.sendOtp()`. That repository calls `client.auth.signInWithOtp(phone: phone)`. In the installed GoTrue Dart SDK (`2.27.2`), `signInWithOtp` is `Future<void>`: it posts to the Auth `/otp` endpoint and returns no provider delivery receipt to the app. A completed future therefore does not prove that an SMS reached the provider, carrier, or handset. The prior UI headline “Code request received” could still be read as delivery confirmation.

I changed the headline to **“Request accepted”** and the supporting text now says that the request was processed but SMS delivery to the device is not confirmed. The UI advises checking the number and waiting before retrying because rate limits may apply. The provider-error path remains sanitized and actionable; the UI does not surface raw Auth/provider payloads or secrets.

The current error mapper handles retryable network failures, HTTP 429/rate-limit indications, malformed phone numbers, SMS/provider failures, expired or invalid codes, and a generic safe fallback. The current phone normalizer accepts Indian local, `91`, `0091`, and `+91` forms, validates ten digits beginning 6–9, and passes E.164 `+91…` to Supabase.

## What was and was not verified

The existing `supabase/config.toml` contains both `919876543210 = 123456` and `+919876543210 = 123456` under `[auth.sms.test_otp]`. Supabase documents this as a local test mapping; for a mapped number, the Auth service accepts the mapped code without sending SMS. The mapping only applies when requests reach a local Auth service configured with it. [3] [4]

The local Auth/API port `127.0.0.1:54321` and Postgres port `127.0.0.1:54322` both returned **closed**. Docker was not used. The Flutter `AppConfig` defaults to the hosted project URL `https://zbofzjnjgyfuistzomtt.supabase.co`; it uses Dart `--dart-define` overrides, not the root `.env` file. Therefore the fixed mapping is not active in the default mobile build.

The no-SMS widget harness passed. It reads the mapping, enters a local ten-digit phone number, verifies that the fake Auth receives the normalized E.164 number, creates an in-memory fake session, loads the profile, constructs a new controller to exercise app restoration, and signs out. **This is not a live Supabase Auth test** and does not exercise Supabase SDK secure-storage persistence. No OTP request was sent to hosted Auth.

The full Flutter suite passed (**12 tests**), and `flutter analyze lib test` reported **No issues found**. The updated debug APK built successfully at `apps/mobile/build/app/outputs/flutter-apk/app-debug.apk`.

## Logs and provider configuration

The Supabase project Logs page was opened at the official Logs route. The UI reported **“Failed to retrieve logs — Error: No access token provided.”** Its displayed zero counts are not evidence that there were no Auth attempts; the log request itself failed. I did not inspect actual hosted Auth events or provider delivery logs.

The Sandbox connector check found the Supabase MCP connector disabled with `authorization_required`, and the Supabase API connector disabled. Neither was enabled or authorized. The desktop Supabase dashboard session is not signed in. A browser sign-in handoff was requested, but no sign-in was completed in this run.

The local config and environment templates inspected contain no SMS-provider configuration. The project’s root `.env` has Supabase variable names, but its values were not read or printed; no Twilio/SMS provider variable names appeared in the inspected env files. This does **not** establish that hosted Supabase has no provider configured—the provider selection and credentials may exist only in hosted Auth settings.

The newly attached `pasted_content.txt` is a broad vendor/admin portal prompt, not a provider log. Its OTP section asserts that a Twilio error **21704** was recorded, but supplies no raw log row, timestamp, Message SID, or account context; I cannot independently verify that the event belongs to this project or environment. The user has now supplied Messaging Service SID `MG6366490b83e0b1c2f6a76f0a8848f3ba` and says sender `+19413927827` is already in its Sender Pool; these identifiers and membership were not independently checked in Twilio Console. Twilio's [official 21704 documentation](https://www.twilio.com/docs/api/errors/21704) defines it as a Messaging Service with **no available senders** in its Sender Pool. By contrast, [error 21703](https://www.twilio.com/docs/api/errors/21703) means senders exist but none can serve the destination/message type. If that sender is in the exact service and active now, the reported 21704 still needs reconciliation against the event timestamp, sender status then, the exact SID/account or subaccount configured in Supabase, and the raw Twilio error. For a +91 destination, sender membership alone does not establish country eligibility; check Twilio's [international SMS guidance](https://www.twilio.com/docs/messaging/guides/sending-international-sms-guide) as well. No sender was added or purchased, and no Twilio settings were changed.

Supabase documents configurable SMS limits. The published defaults include 30 SMS per project per hour, one OTP request per user per 60 seconds, and up to 30 `/auth/v1/otp` requests per IP per 5 minutes; the actual project settings were not accessible. These are defaults, not evidence of this project's configuration. [2] The app handles rate-limit errors without showing raw responses. No rate-limit setting was changed.

## Exact blockers and next actions

1. **Hosted Auth logs:** Sign in to the already-open Supabase dashboard through the browser takeover, then inspect the project Logs page with Log Type set to Auth and the time range covering the user's failed request. The current lack of an access token blocks this. No OTP needs to be sent to inspect existing logs.
2. **Provider delivery logs:** Verify whether the supplied Twilio 21704 assertion is a real event for this project, then compare Supabase Auth's configured Messaging Service SID and Twilio account/subaccount with the supplied SID, and confirm the sender was present and available at the event time. Inspect the matching Twilio log and, for +91 recipients, country/sender eligibility. Provider-console access is still needed. Do not add or purchase a sender or change provider settings without explicit authorization. Do not infer delivery from the Auth client call.
3. **Real local fixed-OTP integration:** A non-Docker local Supabase Auth/Postgres endpoint must be made available. With the AVD, configure the app to use that endpoint (normally `http://10.0.2.2:54321`) and its local publishable key, then verify request, mapped OTP, SDK session persistence, profile load, and logout. The current closed ports prevent this test; the fake harness is the only verified no-SMS flow so far.
4. **Live SMS:** No real SMS was sent. Any live delivery test remains blocked until the user explicitly authorizes a specific test request and its destination.

No hosted settings were changed, no migrations were applied, and no SMS was requested or sent.

## References

[1]: https://supabase.com/docs/guides/auth/phone-login "Supabase Phone sign-in"
[2]: https://supabase.com/docs/guides/auth/rate-limits "Supabase Auth rate limits"
[3]: https://supabase.com/docs/guides/local-development/cli/config "Supabase CLI local configuration"
[4]: https://supabase.com/docs/guides/self-hosting/self-hosted-phone-mfa "Supabase test OTP behavior"
[5]: https://supabase.com/docs/guides/observability/logs "Supabase Logs in Studio"
[6]: https://supabase.com/docs/guides/auth/audit-logs "Supabase Auth audit logs"
