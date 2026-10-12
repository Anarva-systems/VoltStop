# Phase 23 Infrastructure Trust Audit

Date: 2026-10-03. No services were contacted. No credentials or production data were used.

## Dependency assessment

| Dependency | Identity | Isolation | Credentials configured | Connectivity evidence | Status |
|---|---|---|---|---|---|
| PostgreSQL | Unknown local listener, PID 18132; process lookup returned access denied | Unproven | No staging DB URL in process environment; `.env.integration.local` absent | TCP port 5432 open only; no PostgreSQL handshake/query | **BLOCKED** |
| Redis | Unknown listener, same PID 18132 | Unproven | No staging Redis URL in process environment | TCP port 6379 open only; no `PING` or key operation | **BLOCKED** |
| Supabase | No project ref/URL/keys available | No staging project identified | Missing | Ports 54321/54322 closed; CLI unavailable | **BLOCKED** |
| API | FastAPI application exists; staging config is absent | No staging deployment identified | Missing | Port 8000 closed; API was not started | **BLOCKED** |
| Worker | No worker directory, service, or Redis consumer found | Not applicable | Not applicable | Not applicable | **NOT APPLICABLE** |
| Razorpay | No provider account/config evidence | Test mode unconfigured | Missing test key/secret/webhook secret | No provider connection | **BLOCKED** |

The local ports are not accepted as identity evidence. Their shared listener process could not be identified, so even harmless DB/Redis protocol calls were avoided. No service identity, version, database name, Redis version, auth mode, or environment label was obtained.

## Migration and schema trust

The repository contains five ordered Supabase migrations, latest `202610020005_dispute_hardening.sql`. Applied/pending/failed status is **UNKNOWN** because there is no verified target or migration ledger query. Staging schema, roles, RLS, constraints, ownership links, and migration lock state were not inspected.

## API/web connectivity

The API was not started because it could not safely be configured. Its health route is `/api/v1/health`, but no health, DB, Redis, auth, or basic API request was made. `apps/vendor-web` compiled locally, but its `NEXT_PUBLIC_API_URL` staging value was not configured; local build success is not staging connectivity evidence. No worker is applicable.

## Razorpay

The API now requires an explicit mode in staging/production and rejects a key prefix that disagrees with that mode. Staging requires `test` plus `rzp_test_`; production requires `live` plus `rzp_live_`. This is a local configuration guard only. No provider-supplied mode/credential evidence or webhook registration was available, and no provider request was made.

## Phase 24 boundary

No payment, webhook delivery, refund, dispute, booking concurrency, financial diagnostic, full IDOR/RLS test, synthetic fixture, or persistent audit check was attempted. Phase 24 is not ready until the resource identities and isolation above are established and smoke tests pass.

