# Production readiness status

Date: 2026-10-14

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
policy is configured, and vendor payout transfers are not implemented. The API
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
into the connected Neon database.

The 5% commission settings and payment-capture ledger are defined for new,
verified charging bookings. They do not represent a vendor payout ledger or
transfer. Historic verified charging captures are assigned 0%; hotel and
restaurant orders are outside this commission ledger's scope. The finance page
shows estimates only. There is no connected marketplace transfer/payout
provider, vendor payout ledger, or automated transfer implementation, so no
vendor balance is marked paid.

Before real payments can run, put the PostgreSQL connection string and Razorpay
TEST credentials into the API's ignored local `.env`, then configure a public
HTTPS API and provider webhook before using LIVE credentials. Never place
server credentials in the web or APK environment. Vendor settlement requires a
separate product choice, provider onboarding, ledger and approval flow, and
refund/reconciliation handling.

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
- Restore the API deployment before installing the APK; confirm health,
  readiness, sign-in, and profile loading against authorized real data.
- Build and install a signed Android release with explicit Production API and
  Supabase build arguments using the existing Play signing keystore, then
  verify on a physical device. The keystore is not present in this workspace.
- Complete load, security, privacy/account-deletion, monitoring, backup/restore,
  and rollback checks before claiming production capacity.
