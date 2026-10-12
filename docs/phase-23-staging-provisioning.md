# Phase 23 Staging Provisioning

Audit date: 2026-10-03.

## Result

**BLOCKED — no trusted staging environment was provisioned.** Required cloud credentials/project access, Docker, and staging environment values are unavailable. Local PostgreSQL/Redis listeners remain unidentified. No service connection, database migration, seed, reset, fixture creation, or financial operation was attempted.

## Staging architecture

Repository inspection confirms this architecture:

```text
Flutter driver app ── Supabase Auth / VoltStop API
Next.js vendor/admin web ── Supabase Auth / VoltStop API
FastAPI API ── PostgreSQL (asyncpg), Redis (slot locks), Supabase Auth REST, Razorpay
Supabase migrations ── schema/RLS/roles
Worker ── not present in the repository
```

The existing `docker-compose.yml` declares API and Redis only, has no PostgreSQL service, and requires a local `.env`. Docker is unavailable. No deployment or CI configuration for staging was found. No cloud provisioning identity was supplied, so creating hosted infrastructure was not possible.

## Provisioned services

| Service | Resource identity | Environment | Connectivity | Status |
|---|---|---|---|---|
| PostgreSQL | Local TCP listener PID 18132; executable/process identity inaccessible | Unknown; not proven staging | TCP 5432 accepts connections; no database connection/query made | **BLOCKED** |
| Redis | Same local listener PID 18132; executable/process identity inaccessible | Unknown; not proven staging | TCP 6379 accepts connections; no Redis command sent | **BLOCKED** |
| Supabase | No project URL/keys configured; local ports 54321/54322 closed | None identified | Not attempted | **BLOCKED** |
| API | FastAPI source exists; no staging configuration or API listener on 8000 | None identified | Not started | **BLOCKED** |
| Worker | No worker application/directory/process found | Not applicable | Not applicable | **NOT APPLICABLE** |
| Web | Next.js vendor/admin app exists | Local build only; no staging API URL configured | Build succeeded; runtime/deployment not started | **BLOCKED for staging** |
| Razorpay | No Razorpay test credentials/webhook configuration | None identified | No provider request made | **BLOCKED** |
| Flutter | `apps/mobile`, Dart constraint `>=3.4.0 <4.0.0` | Local SDK unavailable | No Flutter commands run | **BLOCKED** |

No resource IDs or fixture IDs exist for Phase 24. The root `.env` was not read. `.env.integration.local` remains absent.

## Database and migration state

Local files are ordered `202610020001_initial_schema.sql` through `202610020005_dispute_hardening.sql`. The fifth file is the latest. The remote/local service migration ledger and actual schema state are **UNKNOWN**. No migrations were applied or verified. No reset or seed was run. Backup/recovery for a future staging database remains an external infrastructure responsibility.

## Staging configuration changes

- `.env.integration.example` now declares `ENVIRONMENT=staging`, `RAZORPAY_MODE=test`, and the HTTPS vendor portal origin placeholder. It contains placeholders only and cannot be used as credentials.
- The API no longer requests an unused Supabase service-role key. The API validates user sessions through Supabase Auth with the anon key and uses its configured PostgreSQL connection; no source usage of the service-role setting existed.
- API staging/production startup now requires explicit non-local Supabase/PostgreSQL/Redis endpoints, authenticated Redis over TLS, an HTTPS portal origin, required backend settings, and an explicit Razorpay mode/key-prefix match.

These controls improve the safety of a future setup; they do not provision or identify any currently running resource.

