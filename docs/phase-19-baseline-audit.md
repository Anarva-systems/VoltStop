# Phase 19 baseline audit

Audit date: 2026-10-02. Scope: repository structure, local verification, staging readiness, and the Phase 18 dispute/payment foundation. No staging resources were contacted.

## Repository baseline

- API: FastAPI modules for authentication, profile, vendor discovery/portal, route service, slots, bookings, payments, disputes, admin, and financial diagnostics under `apps/api/app`.
- Driver application: Flutter source exists under `apps/mobile`; Google Maps and Supabase client configuration are build-time values. Flutter tooling is unavailable on this machine.
- Vendor/admin web portal: `apps/vendor-web`; no separate `apps/admin-web` project exists. Admin screens are part of the vendor web app.
- Supabase schema: forward migrations `202610020001` through `202610020005`; `supabase/verify.sql` provides baseline structural assertions.
- External integration suite: `apps/api/tests/integration/test_external_services.py` currently checks PostgreSQL connectivity/dispute columns, Redis PING, and Razorpay test credentials only. It does not execute customer/vendor/admin E2E scenarios or apply migrations.
- Local unit/API tests are built around fakes and mocks. They cover selected ownership, admin permission, lock, webhook signature, refund, and idempotency behavior, but do not prove hosted RLS, Redis concurrency, Razorpay webhook delivery, or full booking lifecycle behavior.

## Staging availability

- The integration test gate is `RUN_INTEGRATION_TESTS=1`; the database probe reads `SUPABASE_DB_URL`, Redis uses `REDIS_URL`, and the Razorpay probe uses `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` and skips live-key prefixes.
- No staging credentials were present in the process environment. `.env.integration.local` was absent. The existing root `.env` was not inspected or printed.
- Supabase CLI, `psql`, `redis-cli`, Flutter, and a usable Python interpreter were unavailable. Migration 005 was not dry-run or applied, and no migration ledger was queried.
- No real customer, vendor, admin, booking, refund, or dispute financial data was read or changed.

## Integration template

`.env.integration.example` now lists the app/runtime and verification names: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, `SUPABASE_DB_URL`, `REDIS_URL`, Razorpay test fields, mobile `API_BASE_URL`, web `NEXT_PUBLIC_API_URL`, Supabase web build fields, `RUN_INTEGRATION_TESTS`, and the descriptive `INTEGRATION_TEST_MODE`. Secrets are placeholders; `.env.integration.local` is already ignored by `.gitignore` (`.env.*.local`). The executable integration gate is `RUN_INTEGRATION_TESTS`; `INTEGRATION_TEST_MODE` is currently documentation-only.

## Local checks

| Check | Result | Evidence / limitation |
|---|---|---|
| Web type/lint check | PASS | `node_modules/.bin/tsc.cmd --noEmit` |
| Web production build | PASS WITH WARNING | `node_modules/.bin/next.cmd build`; Next fallback compiler succeeded after the installed Windows SWC binary failed to load. |
| Python compileall | BLOCKED | No working Python interpreter. `uv` found a stale Chocolatey shim targeting a missing Python 3.12 install. |
| API pytest | BLOCKED | Same missing interpreter; Python test suite did not execute in this turn. |
| Flutter analyze/test | BLOCKED | Flutter CLI unavailable. |
| Hosted integration tests | BLOCKED | No staging environment values in process environment; opt-in suite not run. |

The global `npm` launcher also points at a missing `npm-cli.js`; direct local TypeScript and Next binaries were used instead.

## Baseline disposition

The available local web checks pass. This workspace does not provide evidence for staging schema, policy, integration, migration, payment, or end-to-end behavior. See the payment/webhook and production-readiness audits.
