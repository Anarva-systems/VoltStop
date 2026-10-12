# Booking flow

1. The API validates that the slot and vendor are active, verified and
   available, and reads the price from PostgreSQL (never from client input).
2. `/bookings/lock` creates a short-lived Redis lock keyed by slot ID. Its
   cryptographically random token is bound to the authenticated Supabase user.
3. `/bookings` checks that lock, creates a Razorpay order using the database
   price and creates the pending booking/payment rows in a PostgreSQL
   transaction. The transaction locks the slot row, rechecks its state and
   capacity, and rejects a price change. The Redis lock is released with an
   owner-token compare-and-delete script.
4. The response contains the Razorpay order ID and public key ID; booking
   status remains `pending`. A client-side success callback is not trusted.
5. `POST /api/v1/payments/razorpay/webhook` validates the exact raw-body HMAC
   with `RAZORPAY_WEBHOOK_SECRET`, resolves the internal payment by provider
   order ID, locks booking then payment, verifies the booking/payment pointer,
   stored provider payment ID, INR currency, and server-side amount in paise,
   then applies an allowed state transition atomically. Duplicate captured or
   failed events for the same provider payment ID are acknowledged without
   another event or state change. Captured/refunded states do not regress on an
   older failure event. A same-ID late capture after failure is recorded, but
   does not reconfirm an expired booking. Failed payments expire a pending
   booking.
6. Drivers can list/read only their own bookings and cancel their pending
   bookings. A customer may dispute an eligible paid booking and can read only
   their own disputes.

PostgreSQL row locks and active booking counts remain authoritative; Redis
serializes short-lived attempts but cannot replace database transaction
checks. If a payment is captured after a booking was cancelled/expired, the
payment is recorded but the booking is not reconfirmed; refund reconciliation
uses the audited refund request and approval flow.

## Disputes and refunds

`POST /api/v1/disputes` accepts only booking ID, reason, and description. The
server derives customer, vendor, and amount from the owned booking/payment,
requires an idempotency key, and allows at most one active dispute per booking.
Vendor owners can read and append responses only to their own cases; they cannot
change status or financial records.

Admin status changes append to the dispute timeline and immutable admin audit
log. Full or partial refund requests from a dispute are linked to that dispute
and checked against the server-calculated remaining captured payment amount.
Finance Admin or Super Admin approval then uses the same refund service as the
general refund desk. Signed Razorpay webhooks record completion or failure on
the linked dispute. Dispute actions never directly change payment, booking,
refund, or payout amounts. Financial diagnostics report impossible states and
do not repair them.
