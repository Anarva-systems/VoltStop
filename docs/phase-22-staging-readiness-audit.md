# Phase 22 Staging Readiness Audit

Audit date: 2026-10-03. No production service, customer data, or real financial record was used. The root `.env` was not read.

## Summary

**STAGING: BLOCKED.** No staging configuration is present. A local PostgreSQL port (5432) and Redis port (6379) responded to TCP probes, but both listeners map to the same PID (18132) and Windows denied access to identify that process. Their environment and isolation cannot be proved, so no service connection, migration, fixture creation, or financial operation was attempted. Supabase ports 54321/54322 and API port 8000 were closed during the probe.

## Environment

| Area | Status | Evidence |
|---|---|---|
| Isolated staging target | **BLOCKED** | `.env.integration.local` absent; no configured staging endpoint; no project/account context supplied. |
| Staging environment variables | **BLOCKED** | Checked process variables for Supabase, database, Redis, Razorpay, integration opt-in, and Maps were all absent. Values were not printed. |
| Local PostgreSQL | **BLOCKED** | TCP 5432 open, but listener PID 18132 could not be identified; isolation is unproved. |
| Local Redis | **BLOCKED** | TCP 6379 open, same unidentifiable PID 18132; no Redis command was sent. |
| Local Supabase | **BLOCKED** | Ports 54321 and 54322 closed; Supabase CLI unavailable. |
| Local API | **BLOCKED** | Port 8000 closed; no staging API target configured. |
| Safe integration gate | **PASS (not enabled)** | `RUN_INTEGRATION_TESTS` absent; integration probes skipped and made no external request. |

## Infrastructure

Docker, Docker Compose, Supabase CLI, `psql`, `postgres`, and `redis-cli` are unavailable. `docker-compose.yml` defines API and Redis, but not PostgreSQL. Since the open local service owner is unidentified and no isolated staging project was supplied, provisioning or attaching to it is not safe to certify.

## Database and migrations

The local migration files are ordered `202610020001_initial_schema.sql` through `202610020005_dispute_hardening.sql`; `202610020005_dispute_hardening.sql` is the latest. The actual database migration ledger and applied/missing state are **UNKNOWN / BLOCKED**. No schema, extensions, roles, constraints, or RLS policies were queried. No migration was dry-run or applied.

The repository uses entities including `profiles`, `vendors`, `charging_slots`, `bookings`, `payments`, `refunds`, `disputes`, `dispute_events`, `booking_events`, `notifications`, and `admin_audit_logs`. Dispute messages are represented by dispute events; no separate `dispute_messages` table was established. This is local project evidence only, not staging schema evidence.

## Redis

**BLOCKED.** Port 6379 is open but cannot be tied to an isolated test Redis. Slot-lock create/expiry/release, contention, and idempotency were not exercised against Redis.

## Supabase

**BLOCKED.** No staging URL or Supabase keys are configured, the local Supabase listeners are closed, and the CLI is unavailable. Auth, RLS, hosted roles, migration state, and hosted ownership isolation were not tested.

## Razorpay

**BLOCKED.** No Razorpay test key, test secret, or webhook secret is configured. No provider order, test payment, refund, or provider webhook was created or received.

## API

Backend unit/API regression passed locally (60 passed, 3 external-service skips). No API server or staging endpoint was available for integration/E2E requests. Local test doubles are not staging evidence.

## Web

**PASS WITH WARNING (local build only).** `apps/vendor-web` TypeScript validation completed successfully. The Next production build completed and generated its routes using fallback compilation after the bundled Windows SWC module failed to load. No deployment or hosted API connection was tested.

## Flutter

**BLOCKED.** `apps/mobile/pubspec.yaml` requires Dart `>=3.4.0 <4.0.0`; neither Flutter nor Dart CLI is installed. `flutter pub get`, `flutter analyze`, and `flutter test` could not run.

## Configuration and secrets

The integration template contains blank/placeholder configuration. `.env.integration.local` is absent and `.gitignore` excludes `.env.*.local`. The root `.env` was not read. A source/config scan reported no populated provider secrets, private-key headers, or live Razorpay keys; matches were blank values in `.env.example` and synthetic test fixtures. **Git tracking/staging status is unverified** because this workspace has no `.git` metadata, so a Git status or index check could not be performed.

`Settings` currently defaults the environment to `development`, database and provider secrets to empty strings, and Redis to a local unauthenticated URL. No production-mode startup validation was observed in the reviewed settings class. Production secret presence, strength/separation, TLS, and deployment-mode enforcement remain **BLOCKED / NOT VERIFIED**; no production configuration was loaded.

## Observability and recovery

Source has application logging, including exception logging, but no staging log sink, retention, redaction behavior, alerting, or log events were exercised. **BLOCKED.** No backup or recovery mechanism was found in the repository; mark **NOT VERIFIED — external infrastructure responsibility**.

## Performance sanity

**BLOCKED.** No safe staging API/DB/Redis target existed for booking, slot-lock, payment, webhook, refund, or dispute latency checks. No SLA or load-test claim is made.

## Exact local evidence

- Full backend: `60 passed, 3 skipped, 0 failed`.
- Phase 20 repository security tests: `13 passed, 0 skipped`.
- Focused API webhook tests: `4 passed, 42 deselected`.
- External-service integration probes: `3 skipped` because the explicit gate and service values are absent.
- Python `compileall apps/api`: exit code 0.
- Web TypeScript check: exit code 0.
- Web production build: completed; fallback compiler used after SWC load failure.
- Flutter checks: unavailable (no Flutter/Dart CLI).
- TCP probes: PostgreSQL 5432 and Redis 6379 open but owner unidentified; Supabase 54321/54322 and API 8000 closed.

