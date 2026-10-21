# Phase 30 — Staging Project Bootstrap

**Date:** 2026-10-20
**Status:** STAGING DEPLOYED AND SMOKE TESTED; WEBHOOK CONFIGURATION REMAINING

## Completed

- Confirmed the new `VoltStop Staging` Supabase project is active and healthy in the Asia-Pacific region.
- Linked the local Supabase CLI workspace to the staging project. The production `VoltStop` project was not modified.
- Reviewed the migration dry run. It contained 15 application migrations, no seed data, and no destructive table drops.
- Applied all 15 migrations with `supabase db push`; then confirmed every local migration version is recorded remotely with `supabase migration list`.
- Ran `supabase db lint --linked --schema public --level error --fail-on error`; the public schema reported no errors.
- Removed a zero-byte ignored temporary file from `supabase/migrations` that the CLI had skipped.

The full database linter reports issues in bundled PostGIS-owned extension routines under the `extensions` schema. Those extension findings do not appear in the VoltStop `public`-schema lint, which passed. Do not edit vendor-managed extension routines as part of application migrations.

## Staging deployment

- Created separate Vercel projects from the VoltStop GitHub repository:
  - `voltstop-staging-web` (root `apps/vendor-web`) → https://voltstop-staging-web.vercel.app
  - `voltstop-staging-api` (root `apps/api`, FastAPI) → https://voltstop-staging-api.vercel.app/api/v1
- Configured the staging API with `ENVIRONMENT=staging`, `RAZORPAY_MODE=test`, the staging Supabase URL and publishable key, the staging project's PostgreSQL transaction-pooler `DATABASE_URL`, a TLS Redis URL, Razorpay test key ID and secret, and `VENDOR_PORTAL_ORIGIN=https://voltstop-staging-web.vercel.app`. `RAZORPAY_WEBHOOK_SECRET` is intentionally unset.
- Upstash free tier supports a single database with only DB 0, so the staging API shares the existing Redis instance using `REDIS_KEY_PREFIX=staging:` (new `booking_lock_prefix` setting; empty default keeps production behavior unchanged).
- The staging website's `NEXT_PUBLIC_API_URL` is `https://voltstop-staging-api.vercel.app/api/v1`.
- Deployment protection disabled on both staging projects for smoke testing.

## Smoke test results (all passed)

- `/api/v1/health` and `/api/v1/ready` return 200; database, Supabase Auth, and Redis reachable.
- Readiness probe `apps/api/scripts/check_staging_readiness.ps1` passes with `-RequirePaymentCheckout`.
- Staging accounts created in Supabase Auth (admin, vendor, customer) and used for sign-in via the API.
- Vendor profile registration → admin vendor-onboarding approval → charging service enablement → availability slot creation → customer slot lock → booking creation.
- Razorpay test-mode checkout completed in a browser (test card 4111 is rejected as an international card by the test business; the Netbanking test bank simulator succeeds). Checkout signature verified through `POST /payments/razorpay/verify`.
- Booking is `confirmed` with `payment_status=captured` and `amount_paid=50.00`, visible to both the customer and the vendor.
- The staging website renders and is wired to the staging API.

## Batch 0 verification on staging (2026-10-21)

- Three additive migrations applied to the staging database via `supabase migration up` (18/18 recorded; new columns and indexes verified through `schema_migrations`/`pg_indexes`).
- Staging API redeployed from local code via the Vercel CLI (root-linked `.vercel` + root `.vercelignore`; the GitHub remote is NOT involved, so no production auto-deploy risk). Latest deployment `voltstop-staging-debyfme7q`.
- Live smoke results: vendor slot creation → customer lock → booking create returned a real Razorpay test order with status `pending`; concurrent duplicate create was absorbed by idempotency (fail-safe 503, no duplicate booking); both abandoned `pending` bookings auto-expired via the new sweep and their slots returned to `available`; `/auth/verify` returned 429 on request 31 of a burst (30/min limit).
- Security headers verified live on staging responses (nosniff, frame-DENY, referrer-policy, permissions-policy; HSTS over HTTPS).
- One live 500 was caught and fixed during this pass: asyncpg rejected an int for `($n::text || ' seconds')::interval`; replaced with a native `$n::interval` + `timedelta` parameter (168/168 backend tests still green).
- Local credential hygiene: smoke credentials/token files are gitignored; verified via `git log --all` and `git ls-tree origin/main` that no credential-bearing file ever reached the repo or remote. The staging DB password (local temp files) was already rotated once; any long-lived Supabase token that existed in the local `scripts/supabase-token.bin` should be revoked in the dashboard as a precaution.

## Remaining staging work

- Configure a staging Razorpay webhook endpoint, set `RAZORPAY_WEBHOOK_SECRET` in the staging API environment, and re-run the readiness probe with `-RequireWebhook`.
- Then proceed with synthetic cancellation and refund verification. No production data or payment was touched during this phase.


