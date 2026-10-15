# Production operations and readiness

## Health checks

- `GET /api/v1/health` is a liveness check. It confirms only that the API
  process can answer requests.
- `GET /api/v1/ready` checks PostgreSQL, Supabase Auth, and Redis. A response
  includes sanitized states for those dependencies and does not include
  credential values. It also reports customer-payment and commission
  capabilities separately; `ready` does not mean checkout or vendor transfers
  are configured.
- Authenticated endpoints validate the user's Supabase access token through
  Supabase Auth when the project's signing key is symmetric. A transport error
  is reported as `AUTH_UNAVAILABLE`; an invalid/expired token is `401`, and an
  Auth provider HTTP failure is `502`. Check the API's sanitized logs and
  `/ready` dependency state before rotating any keys.

## Deploying the API to Vercel

Set the API project's Root Directory to `apps/api`. The root `index.py` exports
the FastAPI ASGI app, and Vercel installs the project's `requirements.txt`.
Configure the API's Production environment variables in Vercel; keep database,
Redis, payment secrets, and Supabase server settings out of the web project and
mobile build. After changing environment values, redeploy the API and confirm
`/api/v1/health` and `/api/v1/ready` before directing clients to it.

Configure the web project's `NEXT_PUBLIC_API_URL` to the active API URL ending
in `/api/v1`, and set the API's `VENDOR_PORTAL_ORIGIN` to the active web origin.
These client values are build-time values, so rebuild the web project after
changing them. Previously used production URLs were deleted and are not valid
deployment targets.

The API defaults to `ENVIRONMENT=production`; local development must explicitly
set `ENVIRONMENT=development`. Required API values
include `SUPABASE_URL`, `SUPABASE_ANON_KEY` or `SUPABASE_PUBLISHABLE_KEY`,
`DATABASE_URL`, TLS `REDIS_URL`, exact `VENDOR_PORTAL_ORIGIN`, and the matching
live payment configuration. Never send secret values through chat or include
them in source control.

For a Vercel deployment that is still using Razorpay test credentials, set
`ENVIRONMENT=staging` and `RAZORPAY_MODE=test` in the deployment's environment
variables. Configure `SUPABASE_URL`, `SUPABASE_ANON_KEY` (or
`SUPABASE_PUBLISHABLE_KEY`), `DATABASE_URL` from Supabase's **Transaction
pooler** connection details (shared pooler, port `6543`), an authenticated TLS `REDIS_URL`
(`rediss://...`), `VENDOR_PORTAL_ORIGIN`, `RAZORPAY_KEY_ID` (`rzp_test_...`),
and `RAZORPAY_KEY_SECRET`. Staging checkout testing does not require
`RAZORPAY_WEBHOOK_SECRET`; leave it unset until signed webhook delivery is
configured. The deployment fails during import if it defaults to production
with test credentials or missing required settings. After changing variables,
redeploy and check `/` and `/api/v1/health`, then `/api/v1/ready`.

Supabase direct database hostnames resolve to IPv6 by default, which Vercel
Functions cannot reach. Use the IPv4 shared transaction pooler connection
string shown by the Supabase dashboard instead; VoltStop disables asyncpg's
statement cache for that pooler and creates the PostgreSQL pool lazily so a
database outage does not prevent the liveness endpoints from starting.

For local payment development, set `RAZORPAY_MODE=test`, `RAZORPAY_KEY_ID`,
`RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET` in the ignored API `.env`.
Use Razorpay TEST values first. Configure the webhook URL against a reachable
HTTPS API at `/api/v1/payments/razorpay/webhook` before expecting asynchronous
payment confirmation. The current application does not configure provider
transfers or a vendor payout ledger.
For a marketplace that collects customer payments and settles vendors, assess
[Razorpay Route](https://razorpay.com/docs/payments/route/) and linked-account
onboarding with Razorpay before implementing live splits. A separate payout
service must not be enabled until its account approval, idempotency, signed
webhooks, finance approval controls, and reconciliation are in place.

## Live charger availability

The existing `charging_slots` table represents dated booking inventory. The
codebase does not yet model operator stations, physical connectors, current
connector state, or provider data freshness. Integrate the provider through a
server-side adapter that normalizes station and connector identity/state,
persists an observed timestamp, and publishes changed records to Supabase
Realtime. Treat stale or missing provider observations as unknown/unavailable
according to the provider's contract. Do not derive current charger availability
from reservation slots.

The provider's API documentation and a sanitized response example are required
to implement the adapter and correctly map authentication, IDs, status values,
rate limits, webhooks/polling, errors, and freshness. Provider credentials must
remain server-side.

## Capacity and release checks

The code does not have verified capacity evidence for thousands of users. A
release capacity claim requires a load test against the selected hosting plan,
PostgreSQL pooler/connection limits, Redis, Supabase Realtime, provider quota,
and realistic request mix. Measure latency, error rate, database connections,
Redis saturation, function concurrency, and stale-data behavior; then set
limits from those results.

Before release, verify a signed-in driver's profile and a real authorized
admin/vendor flow, live provider freshness, payment and webhook reconciliation,
physical-device release behavior, backups and restore, monitoring, rollback,
privacy/account deletion, and store target-API requirements.

Android releases target API 36. Build a Play release with the existing VoltStop
release keystore, Production `API_BASE_URL`, Supabase URL, and Supabase
publishable key. Release builds intentionally fail if the signing properties
are missing; do not substitute Android's debug keystore for the Play signing
key.
