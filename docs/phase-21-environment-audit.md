# Phase 21 Environment Audit

Date: 2026-10-03. No production data or credentials were used. The root `.env` file was not read; Phase 21 integration tests load `.env.integration.local`, which is absent.

## Architecture and payment lifecycle

- FastAPI application in `apps/api`, backed by PostgreSQL/asyncpg, Redis slot locks, Supabase Auth token verification, and Razorpay order/payment/refund operations.
- Booking creation reads slot price from PostgreSQL, creates a Razorpay order, and stores a pending booking/payment. Signed payment webhooks resolve the payment by provider order, lock booking then payment, validate payment ID/currency/amount/relationship, and apply transitions with booking events in a DB transaction.
- Vendors and admins use the same FastAPI service. Admin authorization is database RBAC. Disputes, refunds, booking events, and admin audit records are stored in PostgreSQL; dispute messages are represented in dispute events rather than a separate `dispute_messages` table.
- The driver app is Flutter under `apps/mobile`; vendor/admin web is Next.js under `apps/vendor-web`.
- Supabase has migrations `202610020001` through `202610020005`; local Supabase config expects DB port 54322 and API port 54321. Docker Compose describes API and Redis only; there is no local PostgreSQL service in that compose file.

## Toolchain and dependencies

| Component | Observed | Status |
|---|---|---|
| Python | 3.12.14; matches `apps/api/Dockerfile` (`python:3.12-slim`) | PASS |
| Python dependencies | Installed only `apps/api/requirements.txt` into ignored project `.venv` | PASS |
| pytest | 8.4.2 in `.venv`; API imports (FastAPI, asyncpg, Redis, httpx, pydantic-settings) succeed | PASS |
| Python compile | `.venv\Scripts\python.exe -m compileall apps/api` | PASS |
| Node | v24.21.0 | PASS |
| npm launcher | `npm` cannot load its configured `npm-cli.js` path | BLOCKED (launcher); direct project binaries work |
| Web lint/type check | `apps/vendor-web/node_modules/.bin/tsc.cmd --noEmit` | PASS |
| Web production build | Direct local Next binary completed via fallback compiler | PASS, with SWC warning |
| Flutter/Dart | CLI commands are absent; `pubspec.yaml` declares Dart `>=3.4.0 <4.0.0` | BLOCKED |
| CI config | No `.github/workflows` directory found | SKIPPED (none present) |

The initial isolated install was blocked by sandbox network policy; after an approved dependency download, only the declared API requirements were installed into `.venv`. No global packages were installed. No repository manifest or API implementation was changed for environment recovery.

## Local integration infrastructure

- No Docker or Docker Compose executable is available.
- No `psql`, `postgres`, `redis-cli`, or Supabase CLI is available.
- Local listeners were checked and were not present: Supabase API 54321, Supabase PostgreSQL 54322, PostgreSQL 5432, Redis 6379, and API 8000.
- No process environment values were present for Supabase URL/keys, `SUPABASE_DB_URL`, `DATABASE_URL`, `REDIS_URL`, Razorpay credentials/secrets, `RUN_INTEGRATION_TESTS`, or Google Maps API key. `.env.integration.local` does not exist.
- The integration suite therefore collected and skipped its three external probes (Supabase PostgreSQL/schema, Redis PING, Razorpay test credentials). None contacted external services.

## Hosted staging and migration state

No isolated staging endpoint/account was configured for this run. Migration `202610020005_dispute_hardening.sql` was not applied, dry-run, or checked against a migration ledger. No database schema, RLS policy, role, user, or financial record was queried. The actual hosted migration state is **BLOCKED / UNKNOWN**, not inferred from local migration files.

## Verification commands and results

- Targeted Phase 20 repository tests: 13 passed.
- Targeted API webhook tests: 4 passed (42 unrelated API tests deselected by the targeted filter).
- Full backend suite: 60 passed, 3 skipped, 0 failed.
- External integration suite: 3 skipped because its explicit enable flag and staging service values were absent.
- Python compile: PASS.
- Direct TypeScript lint and Next production build: PASS; npm wrapper failure and SWC fallback warning recorded above.
