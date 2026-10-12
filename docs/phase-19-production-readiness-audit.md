# Phase 19 production-readiness audit

Audit date: 2026-10-02.

## Status by area

| Area | Status | Findings |
|---|---|---|
| Local web portal | PASS WITH WARNING | Type check and production build pass. Next falls back because the installed Windows SWC binary is invalid. |
| Python API | BLOCKED | Python interpreter unavailable; pytest/compileall could not run in this environment. Earlier Phase 18 baseline recorded 45 passed, 3 skipped, but that is not a Phase 19 rerun. |
| Flutter driver app | BLOCKED | Flutter SDK unavailable; no analyze/test run. |
| Supabase schema/migrations | BLOCKED | No staging connection, Supabase CLI, or DB client. Migration `202610020005_dispute_hardening.sql` was not dry-run, applied, or verified in the migration ledger. |
| Supabase auth and RLS | BLOCKED | JWT subject scoping and migration policy/revocation SQL were inspected; hosted customer/vendor/admin isolation was not tested. |
| Redis locking | PARTIAL/BLOCKED | Mock-based lock ownership/reuse/conflict tests exist; real Redis concurrency, expiry, and outage behavior were not tested. |
| Razorpay/payment | PARTIAL/BLOCKED | Signature, pending booking, and refund behavior have mock tests; real test-mode provider/webhook flow was not run. |
| Full booking/dispute/refund E2E | BLOCKED | No staging users, vendor fixture, slot fixture, or provider credentials. Current external suite does not implement these flows. |
| Financial consistency | PARTIAL | Read-only diagnostics check booking/payment/refund consistency; scan is capped at 5,000 and reports truncation. Payout consistency is unavailable because there is no payout ledger. |
| Performance/indexes | PARTIAL/BLOCKED | Migration SQL defines indexes for vendor location and the disputed/booking/admin paths. No live EXPLAIN or load test was performed. |
| API errors/retry UX | PARTIAL | API has standard error envelopes and web portal builds. Runtime outage and retry states were not exercised end to end. |

## Role matrix from migrations

Role grants are loaded from `202610020004_admin_platform.sql`, then `202610020005_dispute_hardening.sql` adds diagnostics permission to finance and super admins. Admin identity and permissions are resolved by the API from `admin_users`; a browser-provided role is not authoritative.

| Role | Granted permissions |
|---|---|
| SUPER_ADMIN | All permissions present in `admin_permissions`, including financial diagnostics |
| OPERATIONS_ADMIN | Dashboard; vendor read/manage; onboarding manage; booking read; operations read |
| FINANCE_ADMIN | Dashboard; transactions; vendor financial summaries; payouts; refund read/create/approve; financial diagnostics |
| SUPPORT_ADMIN | Dashboard; booking read; dispute read/manage |
| VENDOR_MANAGER | Dashboard; vendor read/manage; onboarding manage |

Local mocked tests exercise selected denial/allow cases. Live admin provisioning and policy enforcement remain unverified.

## Data protection and money controls

- Backend uses the JWT-verified subject for customer profile/booking/dispute queries and vendor owner scope for portal queries; selected IDOR cases are covered by test doubles.
- Migration SQL enables RLS/revokes direct client access for admin/dispute records and installs immutable triggers for admin audit and dispute events. Triggers/privileges were not inspected on a live database.
- No payout ledger, automated reconciliation, or payout consistency verification exists in this codebase.
- No external financial data or production provider credentials were accessed.

## Required before production

1. Provision an isolated staging Supabase project/database, Redis, Supabase Auth test accounts, vendor/slot fixtures, and Razorpay test-mode credentials.
2. Review migration 005 against the staging schema/data, run a dry-run, apply only to that staging target, and verify the migration ledger plus `supabase/verify.sql` and new dispute controls.
3. Expand and run staging E2E cases for customer/vendor/admin isolation, route/vendor discovery, slot contention/expiry, booking, captured/failed payment, refund, dispute, replay/idempotency, audit immutability, RBAC, and API errors.
4. Fix and regression-test the captured-payment webhook replay ID mismatch documented in `phase-19-payment-webhook-audit.md`.
5. Run Python and Flutter checks in an environment with supported toolchains; run performance/index checks on staging data.

## Readiness

NOT READY for production. Required integration evidence and core verification are unavailable, and a payment webhook replay validation gap was identified.
