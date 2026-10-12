# Phase 19 payment and webhook audit

Audit date: 2026-10-02. Review is code/test-double based; no live or staging Razorpay calls were made.

## Observed payment path

1. Booking creation requires a lock token bound to the authenticated user, reads the slot on the server, requests a Razorpay order using the server-side amount, and records a pending booking/payment.
2. The browser/mobile response marks payment pending. Booking confirmation is performed by the webhook path, not by a client success callback.
3. `/api/v1/payments/razorpay/webhook` verifies `X-Razorpay-Signature` with an HMAC-SHA256 comparison before parsing the event. Captured/failed payment updates are transaction-scoped, validate amount, and update payment, booking, and event records together.
4. Refund webhook events are mapped to local status and amount-checked against the linked payment/refund. Unknown event types are acknowledged without processing.

## Evidence from local tests and code

- Existing unit/API tests cover valid/invalid webhook signatures, a signed refund webhook, pending booking creation before webhook confirmation, booking lock ownership/reuse, and selected refund/dispute idempotency. These use fakes and do not exercise PostgreSQL transaction/isolation behavior.
- Razorpay external integration probe is read-only and accepts `rzp_test_` credentials only. It checks API credentials, not order creation, captures, refunds, webhook delivery, or signature configuration.
- Payment flow does not trust client-side success for booking confirmation.

## Risks and unverified behavior

- The webhook path and booking lifecycle were not exercised against staging services, a provider webhook, or a migrated PostgreSQL database.
- In `process_payment_webhook`, an already-captured payment is treated as idempotently complete before comparing the incoming payment ID with the recorded Razorpay payment ID. A signed but inconsistent replay for the same order can therefore be acknowledged as processed. This deserves a focused backend fix and regression test before production.
- Payment provider order creation and local booking persistence are separate systems. A DB failure after order creation can leave an orphan provider order; no reconciliation job/ledger was found in scope.
- No payout ledger exists; financial diagnostics explicitly report `payout_check_available: false`.
- Refund webhook status transitions, duplicate/reordered provider events, and real dispute-to-refund booking lifecycle were not verified end to end.
- Production credentials and production financial data were not used.

## Result

Code-level checks: PARTIAL. Staging/provider confirmation: BLOCKED. Do not treat this audit as Razorpay integration certification.

## Phase 20 resolution record

- **Original finding:** an already-captured order could acknowledge a validly signed replay with a different provider payment ID.
- **Root cause:** captured-state idempotency returned before comparing the incoming provider payment ID with the ID stored on the locked payment row.
- **Fix:** Phase 20 validates order/payment/booking association, any previously bound provider payment ID, currency, and server-side paise amount before idempotency/state handling. Captured/refunded states are terminal against older failure events. Payment/refund rows and booking/payment association are checked under the existing transaction and lock order.
- **Regression coverage:** deterministic repository tests and signed-webhook API tests were added, including wrong ID with unchanged state, amount below/above, currency/order/booking mismatch, duplicate/triple replay, concurrent replay simulation, out-of-order failure, and late capture after failure.
- **Verification:** Python `compileall` PASS. Web TypeScript check and production build PASS (Next fallback compiler warning). Targeted and full pytest runs are BLOCKED before collection because the available Python runtime has no `pytest` package.
- **Remaining limitation:** the repository tests have not executed, and no PostgreSQL/Razorpay staging test was available. The concurrent unit case serializes a fake transaction; it does not prove real PostgreSQL locking under contention.
