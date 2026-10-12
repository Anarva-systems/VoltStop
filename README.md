# VoltStop

VoltStop is an EV journey and pitstop booking platform foundation for the
Srikakulam ⇄ Vijayawada NH-16 pilot corridor. The repository contains a Flutter
driver app, Next.js vendor web app, FastAPI service, Supabase schema, and Redis
development service. Payment, authentication, maps, and booking integrations
are deliberately not simulated or presented as active.

## Prerequisites

- Python 3.12+ and pip
- Node.js 20.9+ and npm
- Flutter stable (Dart 3.4+)
- Docker Compose v2
- Supabase CLI (optional, for local Supabase/Postgres)

## Start the API

From the repository root:

```sh
cp .env.example .env
python -m venv apps/api/.venv
# macOS/Linux
. apps/api/.venv/bin/activate
# Windows PowerShell: apps/api/.venv\\Scripts\\Activate.ps1
pip install -r apps/api/requirements.txt
uvicorn app.main:app --app-dir apps/api --reload
```

Health check: `http://localhost:8000/api/v1/health`; interactive docs:
`http://localhost:8000/docs`.

## Start Redis and API with Docker

```sh
cp .env.example .env
docker compose up --build
```

The API listens on port 8000 and Redis on port 6379. Compose does not run a
standalone PostgreSQL container: Supabase local provides PostgreSQL and its
services. Redis is currently infrastructure only; no booking lock endpoints
are exposed until their persistence/transaction contract is implemented.

## Start Supabase (local)

Install Supabase CLI, then from the repository root:

```sh
supabase start
supabase db reset
```

The migration in `supabase/migrations` enables PostGIS and creates the
platform schema. `supabase db reset` applies migrations and the fictional
development corridor seed. Verify the result with:

```sh
psql "postgresql://postgres:postgres@localhost:54322/postgres" -v ON_ERROR_STOP=1 -f supabase/verify.sql
```

Copy local Supabase API URL and anon/service-role keys from `supabase status`
into `.env`. Keep service-role and payment secrets private; never use them in
client applications. For hosted projects, link the project and use the normal
Supabase migration workflow instead of `supabase start`.

## Start the vendor web app

```sh
cd apps/vendor-web
npm install
npm run dev
```

Copy `apps/vendor-web/.env.example` to `apps/vendor-web/.env.local`, then set
the Supabase URL and public anon key. Set `NEXT_PUBLIC_API_URL` if the API is
not at `http://localhost:8000/api/v1`, and set backend `VENDOR_PORTAL_ORIGIN`
to the portal origin. Open `http://localhost:3000/vendor/login`. Vendor sign-in
uses Supabase email/password sessions; vendor profile, dashboard, bookings,
slots, services, and revenue are read and updated through owner-scoped API
endpoints. New business profiles remain hidden until VoltStop verifies and
activates them.

For the deployed VoltStop portal, set the vendor-web project's Production
`NEXT_PUBLIC_API_URL` to `https://api-one-nu-41.vercel.app/api/v1` before
building. Set the API project's Production `VENDOR_PORTAL_ORIGIN` to
`https://vendor-web-xi.vercel.app`. Keep the backend in `ENVIRONMENT=production`
and provide its required database, Supabase, Redis, and payment settings there;
do not place backend credentials in the frontend project. Preview and local
deployments should use their own API and portal origins. The web client now
fails with a configuration message if a non-development build has no API URL,
instead of silently calling localhost.

For the Vercel Vendor Web project, set the Root Directory to `apps/vendor-web`
and use the Next.js build command `npm run build`. Configure Production
Supabase values from the same project: either use
`NEXT_PUBLIC_SUPABASE_URL` with `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` (or the
legacy `NEXT_PUBLIC_SUPABASE_ANON_KEY`), or use the Supabase integration names
`SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`. The build maps only URL,
publishable-key, and anon-key values into the browser bundle; service-role and
secret keys are never mapped. These are build-time values, so redeploy the
Production deployment after changing them.

The same application also serves the internal administrator console at
`http://localhost:3000/admin/login`. Admin login uses Supabase Auth, then the
API checks `public.admin_users` and role permissions on every request. Applying
`202610020004_admin_platform.sql` seeds the role matrix but intentionally does
not grant admin access to any existing user. To provision the first Super
Admin, use a trusted database session after that Supabase Auth account exists:

```sql
insert into public.admin_users (user_id, role_name, is_active)
values ('<existing-auth-user-uuid>', 'SUPER_ADMIN', true);
```

Do not provision admins through a browser form or client-editable user metadata.
Disputes are customer-owned and vendor-scoped; party identifiers and amounts are
derived from bookings. Vendor responses are append-only and do not change case
status or financials. Admin events and audit records are append-only. Refund
requests are submitted for separately audited Finance Admin approval before
the server calls Razorpay. Refund operations require Razorpay server credentials;
ambiguous provider responses remain in processing for reconciliation. Platform commission,
automated vendor payouts, GPS telemetry, and support/complaint systems are not
implemented and are shown as unavailable in the console.

## Start the Flutter mobile app

```sh
cd apps/mobile
flutter pub get
flutter run \
  --dart-define=SUPABASE_URL=https://YOUR_PROJECT.supabase.co \
  --dart-define=SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLISHABLE_KEY \
  --dart-define=API_BASE_URL=http://localhost:8000/api/v1
```

On Android emulators, use `http://10.0.2.2:8000/api/v1` instead of
`localhost`. Driver profiles, route history, road-route estimates, pitstop search,
and booking history use Supabase directly with owner-scoped RLS. Route geometry and
distance come from OpenStreetMap's OSRM service, while pitstop matching uses the
PostGIS `route_pitstops` RPC. The app still uses the trusted API for slot locks,
booking/payment creation, cancellation, disputes, and signed Razorpay webhook
processing; these operations are not safe as unrestricted client table writes.
Keep Supabase service-role keys and Razorpay secrets on the server. Phone OTP on
hosted Supabase also requires enabling the phone provider and configuring an SMS
provider in the project dashboard. Local Supabase uses the fixed test OTP mapping
in `supabase/config.toml`, so local tests do not send real SMS. Route and battery
values remain explicitly approximate.

## Apply Supabase migrations

Migrations are forward-only. Do not edit or replay old migrations against a
hosted project. Migration `202610020005_dispute_hardening.sql` adds the dispute
party/amount fields, immutable event controls, and refund linkage. To apply all
pending migrations to the intended hosted Supabase project:

```sh
supabase login
supabase link --project-ref <project-ref>
supabase db push --dry-run
supabase db push
supabase migration list --linked
```

Stop on any migration error and inspect it before retrying. The migration
intentionally fails if multiple active disputes already exist for a booking;
review those rows and decide on a data correction explicitly. This workspace
has not connected to or applied migrations to a hosted database.

For opt-in integration checks, copy `.env.integration.example` to
`.env.integration.local`, fill in dedicated test services, set
`RUN_INTEGRATION_TESTS=1`, then run `pytest apps/api/tests/integration -v`.
Razorpay integration accepts only `rzp_test_` keys. The regular backend suite
uses test doubles and makes no external service claims.

## Checks

```sh
python -m pytest apps/api/tests
cd apps/vendor-web && npm run build
cd apps/mobile && flutter test
```

Consult `docs/development.md` for configuration, `docs/architecture.md` for
module boundaries, and `docs/booking-flow.md` for the intended transaction
lifecycle and unfinished concurrency/payment gates.
