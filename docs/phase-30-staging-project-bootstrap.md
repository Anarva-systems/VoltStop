# Phase 30 — Staging Project Bootstrap

**Date:** 2026-10-20
**Status:** SUPABASE SCHEMA READY; STAGING API DEPLOYMENT PENDING

## Completed

- Confirmed the new `VoltStop Staging` Supabase project is active and healthy in the Asia-Pacific region.
- Linked the local Supabase CLI workspace to the staging project. The production `VoltStop` project was not modified.
- Reviewed the migration dry run. It contained 15 application migrations, no seed data, and no destructive table drops.
- Applied all 15 migrations with `supabase db push`; then confirmed every local migration version is recorded remotely with `supabase migration list`.
- Ran `supabase db lint --linked --schema public --level error --fail-on error`; the public schema reported no errors.
- Removed a zero-byte ignored temporary file from `supabase/migrations` that the CLI had skipped.

The full database linter reports issues in bundled PostGIS-owned extension routines under the `extensions` schema. Those extension findings do not appear in the VoltStop `public`-schema lint, which passed. Do not edit vendor-managed extension routines as part of application migrations.

## Remaining staging work

The database schema is ready, but there is no staging API deployment yet. Configure the Vercel staging API with:

- `ENVIRONMENT=staging` and `RAZORPAY_MODE=test`
- the staging project's `SUPABASE_URL` and public/anon key
- the staging project's PostgreSQL transaction-pooler `DATABASE_URL`
- an isolated TLS Redis URL
- Razorpay test key ID and secret, stored only in the API environment
- an optional test webhook secret after a staging webhook endpoint is configured

After deployment, run `apps/api/scripts/check_staging_readiness.ps1` against the staging API with `-RequirePaymentCheckout`. Add `-RequireWebhook` only after webhook configuration is complete. Then proceed with synthetic booking, cancellation, checkout, and refund verification. No production data or payment was touched during this phase.
