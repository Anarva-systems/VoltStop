# Phase 20 security review

## Reviewed path

`apps/api/app/payments/router.py` → `Database.process_payment_webhook` / `Database.process_refund_webhook` in `apps/api/app/core/database.py` → existing PostgreSQL `payments`, `bookings`, `refunds`, and `booking_events` records.

## Controls verified in code

- Raw webhook body signature is verified with HMAC-SHA256 and constant-time comparison before JSON parsing or DB access. Missing/invalid signature is rejected.
- Payload IDs and currency are required to be non-empty strings; paise amounts must be positive JSON integers (booleans/floats/strings are rejected). Client-supplied amounts and booking/customer/vendor IDs are not accepted by this endpoint.
- Payment is resolved by the stored provider order ID. The booking is locked by the stored booking ID and matching payment pointer; the payment row is then locked and its stored booking/order links are rechecked.
- An existing provider payment ID must match. The same ID cannot already belong to a different payment. Existing unique DB constraints remain the final race guard.
- Currency is checked against the stored INR payment currency, and provider paise are compared to the server-side decimal amount using integer paise conversion.
- Identity, amount, currency, and relationship checks precede replay/state handling. Payment and booking transitions plus booking events remain in one transaction.
- Captured/refunded states are terminal against older failure events; same-ID duplicates return without another state/event write. A same-ID late capture after failure records capture but does not reconfirm an expired booking.
- Refund webhook processing also verifies existing refund ID, parent payment ID, currency, and server-side amount. Repeated same-status events do not write a second audit/dispute event; terminal refund states do not regress.
- Rejection logs contain only error codes. They do not contain webhook signatures, secrets, or credentials. Public errors do not echo stored IDs or internal records.

## State transition matrix

Only `payment.captured` and `payment.failed` mutate payment records. Other payment event types are acknowledged as unprocessed by this endpoint.

| Stored payment state | Incoming event | Result |
|---|---|---|
| `pending` | `payment.captured` | Set `captured`; confirm booking only if it is still `pending`; append payment/confirmation events transactionally. |
| `pending` | `payment.failed` | Set `failed`; expire booking only if still `pending`; append failure/expiry events transactionally. |
| `authorized` | `payment.captured` | Set `captured`; confirm only a still-pending booking. |
| `authorized` | `payment.failed` | Set `failed`; expire only a still-pending booking. |
| `failed` | Same-ID `payment.failed` | Idempotent no-op. |
| `failed` | Same-ID `payment.captured` | Record `captured`; do not reconfirm an already expired booking. |
| `captured` | Same-ID captured or older failed event | Idempotent no-op; no state regression. |
| `refunded` | Same-ID captured or failed event | Idempotent no-op; no state regression. |
| Any state with different already-bound payment ID | Either supported event | Reject before mutation. |
| Any unsupported stored state | Either supported event | Reject safely. |

An event for an unknown provider order or an inconsistent booking/payment pointer returns the existing safe not-found response without mutation. The schema stores INR and constrains it to INR. `authorized` exists in the schema but is not produced by the current webhook handler; its transition behavior is retained for an authorized payment record receiving a supported capture/failure event.

## Concurrency and test evidence

The implementation keeps booking-then-payment `FOR UPDATE` locks, making same-order requests serialize on the booking row. The unique provider-payment constraint covers cross-payment assignment races; a unique violation is converted to a generic safe rejection. New tests exercise the actual repository method against an in-memory transactional SQL double, including concurrent duplicates. This is deterministic unit coverage design, not PostgreSQL concurrency evidence.

Python `compileall` passed. Targeted/full pytest did not execute because `pytest` is absent from the available Python runtime. No staging Postgres, Razorpay test credentials, or real webhook delivery were used. Thus behavior is statically reviewed and tests are authored, but regression outcomes remain unverified until pytest and preferably isolated PostgreSQL tests run.
