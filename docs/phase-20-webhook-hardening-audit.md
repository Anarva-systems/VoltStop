# Phase 20 webhook hardening audit

## Baseline

- Webhook entry: `apps/api/app/payments/router.py`, `POST /api/v1/payments/razorpay/webhook`.
- Provider integration: `apps/api/app/payments/service.py`; creates Razorpay orders with server-side amount and INR and verifies the raw-body HMAC with constant-time comparison.
- Persistence/state transitions: `apps/api/app/core/database.py`, `Database.process_payment_webhook` and `Database.process_refund_webhook`.
- Booking creation: `apps/api/app/bookings/router.py` creates a pending booking and payment through `create_pending_booking`, using DB slot price and provider order ID.
- Payment schema: `supabase/migrations/202610020001_initial_schema.sql`. `payments` stores internal payment UUID, booking UUID, unique Razorpay order ID, unique nullable Razorpay payment ID, INR amount, INR currency, status, and webhook-verified flag. `bookings.payment_id` points to its payment through a deferred composite FK on `(payment_id, id)` referencing `(payments.id, payments.booking_id)`; payments also uniquely reference a booking.
- Refund flow: `apps/api/app/admin/refund_service.py`, `apps/api/app/admin/repository.py`, and `process_refund_webhook`. Refund webhook processing resolves by local/provider refund ID and verifies the parent provider payment ID plus server-side amount. It has row locking and terminal-state checks.
- Events: payment state changes append `booking_events` in the same DB transaction. There is no separate webhook receipt table; replay protection relies on locked payment state, the bound provider payment ID, and database uniqueness.

## Existing webhook validation

The handler verifies the raw-body signature before parsing. Supported payment events are `payment.captured` and `payment.failed`; unsupported event types are acknowledged without processing. The handler extracts provider order ID, provider payment ID, amount in paise, and currency from the signed provider payment entity. It does not accept booking/customer/vendor IDs or amounts from client requests.

The database resolves the internal payment using the provider order ID, locks the related booking and payment, compares amount using integer paise derived from the stored decimal amount, and changes payment/booking state transactionally. The schema stores INR and constrains it to INR.

## Original vulnerability

For an already-captured payment, `process_payment_webhook` returned success before comparing the incoming provider payment ID to `payments.razorpay_payment_id`. This allowed a correctly signed but inconsistent replay for the same order to be acknowledged. The payment row lock prevented duplicate concurrent mutations, but the identity check was ordered incorrectly. The previous handler also omitted currency validation and did not explicitly require the booking's `payment_id` pointer to match the resolved payment in its locking query.

## Intended minimal fix

Validate provider order/payment association, booking/payment pointer, amount, and currency against the locked server-side rows before evaluating replay/state behavior. Require an existing stored provider payment ID to match every replay. Preserve pending-to-captured/failed behavior; permit a same-ID late capture after a failed event so a genuine provider capture is recorded without reconfirming an expired booking; make captured/refunded states terminal against older failure events. Retain booking-then-payment row-lock ordering and existing unique constraints for concurrent duplicate safety. Keep rejected responses generic and log only safe rejection codes, never signatures or secrets.

## Baseline tests/tooling

The existing test suite uses FastAPI `TestClient` and a fake database; it covered booking pending state and webhook signature/refund webhook behavior, but had no payment-capture webhook replay/identity tests. Baseline `python -m pytest apps/api/tests -q` could not start because the available Python runtime has no `pytest` module. `python -m compileall apps/api` passed. No database, provider, or production financial data is used by these checks.
