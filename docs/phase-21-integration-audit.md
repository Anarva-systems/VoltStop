# Phase 21 Integration Audit

Date: 2026-10-03. Evidence is local-only unless explicitly identified otherwise. No mock or unit result below is represented as a service integration.

| Area | Status | Evidence / result |
|---|---|---|
| PostgreSQL staging | BLOCKED | No local ports 5432/54322; no psql, Docker, Supabase CLI, DB endpoint, or integration-local env file. No connection or schema query was made. |
| Migration state | BLOCKED | Migration `202610020005_dispute_hardening.sql` exists in source but was not applied/dry-run; hosted ledger unavailable. |
| Database integrity | BLOCKED | Constraints and indexes were read from local migrations only. No live FK, unique, index, tenant ownership, or audit constraint was checked. |
| Redis staging | BLOCKED | No Redis listener on 6379, redis-cli, Docker, or staging URL. Unit tests cover fake lock behavior only. |
| Supabase Auth | BLOCKED | No staging URL/keys or local Supabase API on 54321. JWT/Auth behavior is covered by local test doubles only. |
| Supabase RLS | BLOCKED | No authenticated database sessions or staging project. Local migrations/revokes were inspected, not exercised. |
| Customer/vendor/admin RBAC | BLOCKED (integration) | Unit suite includes customer/vendor scoping and admin permission cases; hosted role grants and IDOR isolation were not tested. |
| Razorpay test mode | BLOCKED | No `rzp_test_` key, webhook secret, or test account configured. No provider request, order, capture, refund, or webhook delivery occurred. |
| Payment webhook | BLOCKED (external) | Phase 20 security tests passed locally against the repository SQL double and API fake; no provider-signed delivery or live PostgreSQL transaction was tested. |
| Refund webhook | BLOCKED (external) | Local unit tests cover signature/refund mapping/idempotency behavior; no Razorpay test refund/webhook occurred. |
| Financial consistency | BLOCKED (database execution) | Read-only diagnostics code and truncation behavior are documented; no live diagnostics query/data set was run. |
| Audit trail | BLOCKED (database execution) | Booking events and audit/dispute triggers were inspected in source; no database append-only trigger, event row, or hosted audit record was verified. |
| Google Maps / route provider | BLOCKED (external) | Route unit tests use a fake route provider. No Maps key or remote route request was available. |

## Local tests that do not establish integration

- Phase 20 payment repository tests exercise repository logic with a transactional in-memory SQL double; they do not prove PostgreSQL locking or schema behavior.
- API webhook tests use a fake database and test signature handling/response behavior; they do not prove Razorpay sent or signed an event.
- Full suite: 60 passed, 3 skipped, 0 failed. The skipped cases are the three explicitly gated external-service probes.
- The targeted webhook tests: 17 passed, 0 failed, 0 skipped across the repository test file and API webhook-filter run.

## Migration decision

No migration command was run because no isolated staging project/connection was available. This avoids applying a financial/dispute migration to an unknown or production target. Migration status remains BLOCKED/UNKNOWN until a staging project is supplied and its project identity is verified.
