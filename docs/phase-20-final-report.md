# Phase 20 — Payment & Webhook Security Hardening

## 1. Objective

Harden VoltStop's existing Razorpay webhook and database state transitions against provider-ID mismatch, replay, duplicate effects, amount/currency mismatch, relationship mismatch, and out-of-order delivery without replacing the payment system.

## 2. Original Phase 19 Finding

An already-captured payment returned success before comparing the incoming Razorpay payment ID with the ID stored on the payment record.

## 3. Root Cause

`Database.process_payment_webhook` checked `payment_status == captured` immediately after locking rows. The replay return happened before payment-ID association validation.

## 4. Files Changed

- `apps/api/app/core/database.py`
- `apps/api/app/payments/router.py`
- `apps/api/tests/test_api.py`
- `apps/api/tests/test_payment_webhook_security.py` (new)
- `docs/phase-20-webhook-hardening-audit.md` (new)
- `docs/phase-20-security-review.md` (new)
- `docs/phase-20-final-report.md` (new)
- `docs/phase-19-payment-webhook-audit.md`
- `docs/api.md`
- `docs/booking-flow.md`

No UI or migration was changed. Existing unique indexes and booking/payment foreign keys are reused.

## 5. Webhook Validation Flow

The handler now verifies the raw-body signature first, strictly parses provider IDs/paise/currency, resolves the internal payment by provider order, locks the linked booking then payment, validates stored relationships/payment ID/currency/server amount, and only then evaluates replay/state behavior. Rejection logging records safe error codes only.

## 6. Provider Payment ID Validation

An already-bound provider payment ID must match every event. A provider payment ID already bound to another internal payment is rejected; the existing DB unique constraint is the final race guard. Added a regression test for the original captured-payment mismatch and a cross-payment binding case.

**Verification: BLOCKED** — tests were authored but pytest could not collect/run in this environment.

## 7. Order Validation

The provider order ID selects the internal payment and is rechecked on its locked row. Unknown/mismatched order returns the safe not-found response. Added an unknown-order no-mutation test.

**Verification: BLOCKED** — test execution unavailable.

## 8. Amount Validation

Provider amount must be a positive JSON integer in paise and equal the server-side stored INR amount converted to paise. Client-supplied amounts are not used. Added below-expected and above-expected no-mutation cases.

**Verification: BLOCKED** — test execution unavailable.

## 9. Booking/Payment Association

Booking is selected and locked only when its `payment_id` matches the payment resolved by provider order; the locked payment's booking and order links are then rechecked. Existing composite FK remains in place. Added a broken-pointer no-mutation case.

**Verification: BLOCKED** — test execution unavailable; no database integration run.

## 10. Replay Protection

Identity, amount, and currency validation occur before replay returns. Same-ID duplicate events do not write another payment/booking event. Captured/refunded states do not regress on an older failure event. Same-ID late capture after failure is recorded without reconfirming an expired booking.

**Verification: BLOCKED** — duplicate/triple and out-of-order tests were authored but not executed.

## 11. Idempotency

Existing row locks and payment status are reused; no new receipt table or parallel payment system was added. Refund handling now also checks refund ID/currency and skips repeated same-status audit/event writes.

**Verification: BLOCKED** — pytest unavailable; no DB test.

## 12. Concurrent Processing

Same-order transactions preserve booking-then-payment row-lock ordering. A unique provider-payment constraint handles assignment races across different payments, with safe error translation. A concurrent duplicate test uses a fake transaction lock.

**Verification: PARTIAL** — deterministic test authored but not executed; actual PostgreSQL lock/concurrency behavior remains unverified.

## 13. Invalid State Protection

Implemented transition rules are documented in `phase-20-security-review.md`. Captured/refunded are terminal against older events; unsupported states are rejected. Failed-to-captured is allowed only for the same bound provider payment ID and does not reconfirm an expired booking.

**Verification: PARTIAL** — code compiled; state regression tests were authored but not executed.

## 14. Audit Logging

Effective payment state changes continue to append booking events in the same transaction. Rejected payment/refund webhooks log safe rejection codes without signatures or secrets. Repeated refund status no longer duplicates audit/dispute events.

## 15. Regression Tests

Added coverage for wrong stored payment ID with unchanged state, payment ID already linked elsewhere, amounts below/above expected, currency mismatch, unknown order, booking/payment pointer mismatch, duplicate/triple capture, concurrent replay simulation, older failure after capture, late capture after failure, and signed API webhook replay/mismatch behavior.

**Targeted webhook tests:** 0 passed, 0 failed, 0 skipped — **BLOCKED before collection** because `pytest` is not installed in the available Python runtime (`No module named pytest`).

## 16. Full Test Suite

**Full backend tests:** 0 passed, 0 failed, 0 skipped — **BLOCKED before collection** for the same missing `pytest` module. Earlier Phase 19 test results are not claimed as a Phase 20 rerun.

## 17. Build/Lint Results

- Python compile: **PASS** — `python -m compileall apps/api` using the available bundled Python runtime.
- Web lint/type check: **PASS** — direct local TypeScript compiler completed with no errors. The global npm launcher points to a missing `npm-cli.js`, so the local compiler binary was used.
- Web build: **PASS WITH WARNING** — Next production build completed. The installed Windows SWC binary failed to load and Next used its fallback compiler.

## 18. Remaining Blockers

- Pytest must be available in a project-approved test environment to execute targeted and full API tests; no package installation was performed.
- Real PostgreSQL concurrency/transaction behavior remains unverified; tests use a transactional in-memory SQL double.
- Razorpay test-mode integration and staging webhook delivery were not run. No staging credentials/services were available.
- No production readiness, hosted RLS, or staging migration claim is made.

## 19. Security Assessment

**Payment/webhook implementation: PARTIAL.** The known ordering flaw is fixed in code and regression coverage is authored. Signature, provider identifiers, booking/payment relationship, INR currency, server-side amount, row locks, and unique constraints are preserved or strengthened. **Acceptance criteria requiring executed tests remain BLOCKED**, so this phase cannot be considered complete yet.

## 20. Phase 20 Status

**NOT COMPLETE** — code hardening and test authoring are complete, but pytest did not execute, and PostgreSQL concurrency/provider integration evidence is absent.

**Overall production readiness: NOT YET VERIFIED.**
