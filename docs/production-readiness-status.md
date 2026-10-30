# Production readiness status

Date: 2026-10-14, settlement and charger sections updated 2026-10-30

## Current service state

The previously used Production web and API deployments were deleted, so no
public web or API endpoint is available. No public deployment has been created
from this workspace. The local web app is running on `0.0.0.0:3003`; the API is
running on `0.0.0.0:8000` from the updated source in `D:\voltstop`. The current
laptop Wi-Fi address is `10.35.79.182`. The web project's ignored `.env.local`
points to that API address; browser CORS accepts `http://127.0.0.1:3003` and
`http://10.35.79.182:3003`. Native Android requests do not use browser CORS.
The laptop LAN address only works for devices that can reach it on the same
local network; 5G service alone does not make this development API public.

The active local API reports PostgreSQL, Supabase Auth, and Redis reachable.
`GET /api/v1/ready` separately reports payment and vendor settlement capability:
customer payment collection is not configured, the 5% charging commission
policy is configured, and vendor payout transfers are not implemented. That
transfer sentence was true of the 14 October source; the settlement engine now
exists and is reported through the states in **Settlement readiness states**
below, still with no money moving while `VENDOR_SETTLEMENT_ENABLED` is off. The API
environment has a Razorpay key ID, but its mode, server secret, and webhook
secret are not configured. Supabase URL/public keys do not replace those
payment credentials. The application can serve local pages and live database
data, but cannot confirm real customer payments or transfer money to vendors.

The latest mobile error screen reports Vercel's “deployment could not be found”
response. This confirms the current failure is the missing API deployment; the
screen previously mislabeled that Vercel 404 as “Profile not found.” The mobile
client now recognizes `DEPLOYMENT_NOT_FOUND` and names the API deployment as
the issue.

## Authentication failure analysis

The historical `/api/v1/admin/me` response said “Supabase authentication is
unavailable.” In the available API source, that exact response is emitted when
the API's HTTP request to `SUPABASE_URL/auth/v1/user` raises a transport error.
An invalid or expired bearer token is mapped to HTTP 401, and an Auth provider
HTTP error is mapped to HTTP 502. This points to API-to-Supabase connectivity or
deployment runtime configuration, not by itself to a bad mobile publishable or
anon key. The old Vercel deployment and its logs are no longer available, so the
specific DNS, TLS, egress, or runtime cause cannot be proven from the old
request.

The API now records only the Supabase host and transport exception class for
this failure. It does not log the bearer token or API key. `GET /api/v1/ready`
checks PostgreSQL, Supabase Auth health, and Redis, and returns sanitized
dependency states so an API process can no longer appear fully ready while the
Auth or booking-lock dependency is unavailable.

Profile synchronization now avoids rewriting an unchanged profile row on every
authenticated API request, reducing unnecessary database writes under load.

## Payments and vendor settlements

The source contains Razorpay order creation for charging bookings, hotels, and
restaurant orders, mobile checkout, and signature-verified payment/refund
webhooks. Mobile checkout now sends Razorpay's signed result to the authenticated
`POST /api/v1/payments/razorpay/verify` endpoint. The API checks customer
ownership, verifies the HMAC, fetches payment status from Razorpay, and only
reconciles a captured payment. This lets a phone on the laptop's LAN complete a
test without relying on a cloud webhook reaching the laptop. Webhooks remain
the asynchronous reconciliation path when the API is publicly reachable.

The local Razorpay server secret is missing, so manual Checkout cannot create
orders yet. Set `RAZORPAY_MODE=test`, the Test Mode key ID, and the Test Mode key
secret in the API's ignored `.env`. The webhook secret is needed to receive
webhook events and is reported separately by `/api/v1/ready`; it must be
configured before public/staging use. Payment integration tests use synthetic
payment/order records and a mocked provider response; no records were inserted
into the connected Supabase database.

The 5% commission settings and payment-capture ledger are defined for new,
verified charging bookings. Historic verified charging captures are assigned 0%;
hotel and restaurant orders are outside that older commission ledger's scope.

A vendor payout ledger now exists. Migration `202610290003` adds
`vendor_payout_transfers`, one row per captured payment split, with
`source_kind` limited to `charging_booking`, `hotel_reservation`, and
`restaurant_order`, so routing planning covers all three verticals even though
the older per-payment commission ledger only covered charging. `plan_payout`
splits in paise against a single platform rate from
`platform_commission_settings`, honouring a per-vendor override, and refuses
any rate that would leave the platform below the 300 bps retention floor or
above the 5000 bps ceiling. A split is attached to the Razorpay order at
creation and recorded as `planned`; only a signature-verified webhook event
advances a row to processed, settled, failed, or reversed. Nothing in the
codebase marks a vendor balance paid without one of those events.

## Settlement readiness states

`GET /api/v1/admin/settings` reports the platform-wide state as one of four
values:

- `estimate_only` — the payout ledger or the linked-account column is missing;
  apply `202610290003_vendor_payout_routing.sql`.
- `ready_disabled` — the schema exists and routing works in tests, but
  `VENDOR_SETTLEMENT_ENABLED` is off, so every payment stays wholly with the
  platform. **This is the current state and it is a deliberate product gate,
  not a defect.**
- `incomplete` — routing is switched on but payment credentials or the webhook
  secret are missing.
- `routing_enabled` — captured payments split toward verified vendor accounts
  and every transfer is ledgered.

The per-vendor state shown to that vendor in their own portal is narrower and
comes from `payout_status_view`: `routing_enabled`, `ready_disabled`,
`disabled`, `account_required`, `kyc_required`, `approval_required`,
`rate_invalid`, or `profile_required`. Admin revenue pages add a ledger view
of what has actually moved — `calculated_only`, `planned_only`,
`partially_routed`, `routed` — derived from the transfer rows rather than from
an assumption.

KYC is stored masked only: `kyc_pan_masked`, `bank_account_masked`, `kyc_gstin`,
and a provider reference. Uploaded documents and full banking credentials are
never accepted by the API, and the raw PAN or account number is never sent from
either portal.

Before real payments can run, put the PostgreSQL connection string and Razorpay
TEST credentials into the API's ignored local `.env`, then configure a public
HTTPS API and provider webhook before using LIVE credentials. Never place
server credentials in the web or APK environment. Moving real money still
requires a separate product decision to set `VENDOR_SETTLEMENT_ENABLED=true`,
a Razorpay Route-enabled parent account, per-vendor linked accounts with
verified KYC, and a test-mode rehearsal of the transfer, refund, and reversal
paths.

For phone-based test checkout on the local LAN, follow
[`razorpay-test-mode-runbook.md`](razorpay-test-mode-runbook.md). A 5G phone on
a separate mobile network cannot route to the laptop's private LAN address.

## Live charger data

The current app stores dated `charging_slots` for reservations. It does not
contain a normalized station/connector inventory model or a provider sync worker
for physical, current connector state. A charger provider API exists according
to the operator, but its documentation, auth method, webhook/polling contract,
and sanitized sample payload have not been supplied. Integrating without those
would risk showing fabricated availability or mapping the wrong connector
states. The provider adapter and station/connector schema remain blocked on
that contract.

What is now declared rather than live: `vendor_services.supported_connectors`
and `vendor_services.max_power_kw` are vendor-asserted capability fields,
constrained to the six supported plug types, and `driver_vehicles.max_charging_kw`
caps the vehicle side. `route_pitstops` filters on the declared connectors and
the range planner prices a stop at `min(vehicle kW, station kW)`. None of that
is evidence that a plug is present, working, or free right now, and the portals
label an undeclared service as incomplete instead of guessing.

## Notifications and push delivery

SQL triggers already write in-app `notifications` rows. Migration
`202610290004` adds a `push_deliveries` outbox filled by an INSERT trigger, a
`user_push_tokens` table, and adds `notifications`, `hotel_reservations`, and
`restaurant_orders` to the `supabase_realtime` publication so screens can react
without polling. `app/notifications/push.py` drains the outbox with FCM HTTP v1,
claims rows with `FOR UPDATE SKIP LOCKED`, and retries up to six times at 30
second intervals; with no FCM project configured the dispatcher claims nothing
and `GET /api/v1/notifications/push-status` reports it disabled, so local runs
and tests never touch the network.

Push is therefore implemented up to the queue, not end to end. The mobile app
registers and removes tokens over REST but deliberately has no
`firebase_messaging` dependency and no `google-services.json` or
`GoogleService-Info.plist` in the repository, so no build currently obtains a
device token and no notification has been delivered to a real handset. Adding
the native SDK, the platform config files, and a user-consent prompt is a
separate release decision.

## Scale gate

The codebase alone cannot establish a capacity claim for thousands of users.
Capacity depends on the selected API runtime, function/instance concurrency,
PostgreSQL pooler and connection limits, Redis tier, Supabase plan, provider
limits, and request mix. After restoring a staging deployment, run a load test
with measured latency/error rate and database/Redis saturation, then choose
production limits from the observed results. `GET /api/v1/health` is a process
liveness check; use `/api/v1/ready` for database, Auth, and Redis reachability.

## Competitive baseline

Google Play listings checked on 2026-10-13 show the expected feature baseline:

- [Statiq](https://play.google.com/store/apps/details?id=com.statiq): 4.0 stars,
  500K+ downloads; lists real-time charger availability, connector reservations,
  trip planning, and in-app payments.
- [ChargeZone](https://play.google.com/store/apps/details?id=com.chargezone):
  4.6 stars, 500K+ downloads; lists station availability/compatibility, live
  session controls, payments, and session/booking history.
- [PlugShare](https://play.google.com/store/apps/details?id=com.xatori.Plugshare):
  4.6 stars, 1M+ downloads; differentiates with broad station coverage, user
  reviews/photos, and connector/speed/provider filters.
- [Tata Power EZ Charge](https://play.google.com/store/apps/details?id=com.tatapower.evapp):
  3.3 stars, 500K+ downloads; lists reservations, favorites, Auto Charge, and
  trip planning.

Recent public reviews mention charger reliability, failed/released reservations,
billing clarity, and navigation/availability quality. These reviews are
individual reports, not a measured failure rate. For VoltStop, the most valuable
distinction is trustworthy current connector state with a visible observation
time, a recoverable start/stop session flow, reconciled kWh/cost receipts, and
responsive support. The current code does not yet supply live physical charger
state or real charging sessions.

## Local verification

Recorded on 2026-10-14 against the pre-settlement build. The settlement and
notification sections above describe the current source.

- API readiness returned HTTP 200 and reported PostgreSQL, Supabase Auth, and
  Redis reachable. Customer payment collection is `not_configured`, platform
  commission is configured, vendor settlement transfers are
  `not_configured`, and the vendor payout ledger is `not_implemented`.
- The API CORS preflight returned HTTP 200 with the exact allowed origin for
  both localhost and the laptop LAN web origin.
- The running web app returned HTTP 200 for `/login`, `/admin/settings`,
  `/admin/payouts`, `/admin/transactions`, and `/vendor/revenue`.
- The debug APK was rebuilt with
  `API_BASE_URL=http://10.35.79.182:8000/api/v1` and saved as
  `D:\voltstop-1\VoltStop-updated-debug.apk`. This private LAN URL is only for
  same-network testing and will need replacement with a stable HTTPS API URL
  for external users and a Play release.
- One short readiness probe timed out during dependency checks; the next probe
  returned HTTP 200 with all three dependencies reachable. Treat this as a
  transient connection event and keep readiness monitoring enabled; a single
  successful check is not evidence of production reliability.
- Earlier API bytecode compilation and web production-build checks are recorded
  in their CI/release history; no test suite was run as part of this readiness
  check.
- Android: Flutter 3.47.7 built
  `D:\voltstop-1\VoltStop-updated-debug.apk` (updated for the current local LAN
  API URL). The current package is 166,831,931 bytes. It remains a debug build,
  has not been installed on a physical device, and is not suitable for users
  outside the current local network. A Play release still requires the
  existing Play keystore and a stable HTTPS Production API URL.
- No live database, Supabase, payment, or provider write was performed.

The app supports user accounts, but I found no account-deletion path in the
mobile, web, or API source. Google Play requires an in-app deletion option and
an external deletion web resource when an app supports account creation; both
must remove associated user data, subject to clearly disclosed retention
requirements. See [Google Play's account deletion requirements](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en-EN).

## Suite status — 30 October 2026

Executed in this workspace against the current source:

- `pytest tests -q` in `apps/api`: 248 passed, 8 skipped. The skips are the
  Postgres-backed tests that need a real `DATABASE_URL`.
- `npm run lint` (`tsc --noEmit`) and `npx next build` in `apps/vendor-web`:
  clean.
- `npm test` in `apps/vendor-web`: 33 passed, covering the payout view labels,
  the client-side routing validation against the 300 bps floor, the shared
  charger-capability formatter, and the stylesheet coverage guard for every
  state the portals render.

Not executed here: the Postgres-backed tests, `supabase db reset` with
`supabase/verify.sql`, `flutter analyze`, and `flutter test` — no Flutter or
Dart toolchain is present in this workspace, so the push-token client and
notification stream changes are unverified by execution.

## Remaining release gates

- Redeploy the web app and API and confirm `/api/v1/health` and `/api/v1/ready`.
- Confirm all Production API variables are set in the API project and match the
  intended Supabase project; never paste secret values into source or chat.
  The backend requires `SUPABASE_URL`, `SUPABASE_ANON_KEY` or
  `SUPABASE_PUBLISHABLE_KEY`, `DATABASE_URL`, TLS `REDIS_URL`,
  `VENDOR_PORTAL_ORIGIN`, and live Razorpay mode/key/secret/webhook values.
- Confirm the API can validate a real signed-in account token and fetch its
  profile; then exercise the admin/vendor flows against authorized real data.
- Obtain the charger provider API docs and implement/verify ingestion and live
  freshness behavior.
- Verify production Razorpay configuration, webhook delivery, refunds, and
  reconciliation using the provider's approved test/live process.
- Apply migrations `202610290001` through `202610290004` to a real Supabase
  project and re-run the Postgres-backed tests plus `supabase/verify.sql`; the
  slot-window exclusion constraint and the `route_pitstops` overload have only
  been proven against test doubles so far.
- Keep `VENDOR_SETTLEMENT_ENABLED=false` until a product decision, a
  Razorpay Route-enabled parent account, verified vendor linked accounts, and a
  test-mode transfer/refund/reversal rehearsal are all recorded. Then confirm
  `/api/v1/ready` moves from `ready_disabled` to `routing_enabled` and that the
  admin ledger shows the same figures the provider reports.
- Configure an FCM project and service account through the API environment,
  then decide how a mobile build obtains a device token. Until that exists,
  push deliveries stay queued and in-app Realtime remains the only path users
  actually see.
- Restore the API deployment before installing the APK; confirm health,
  readiness, sign-in, and profile loading against authorized real data.
- Build and install a signed Android release with explicit Production API and
  Supabase build arguments using the existing Play signing keystore, then
  verify on a physical device. The keystore is not present in this workspace.
- Complete load, security, privacy/account-deletion, monitoring, backup/restore,
  and rollback checks before claiming production capacity.
