# API conventions

All endpoints use `/api/v1/`. Success responses use
`{"success":true,"data":{},"message":"..."}`. Errors use
`{"success":false,"error":{"code":"...","message":"..."}}`; validation
errors include `details`. FastAPI Swagger docs are at `/docs` in development.

## Implemented endpoints

- `POST /auth/verify`, `GET /auth/me` — access tokens are checked against
  Supabase Auth's `/auth/v1/user`; identity is derived from that response.
- `GET/PATCH /profile` — PATCH accepts only profile fields and uses the
  authenticated user's ID.
- `GET /vendors/nearby?lat=&lng=&radius_km=`, `GET /vendors/{id}`,
  `GET /vendors/{id}/slots`, `GET /slots/{id}`.
- `POST /routes/plan` — accepts the pilot direction in either order, and
  returns map-service distance using OpenStreetMap (OSRM). No
  straight-line or hardcoded route estimate is substituted. A saved vehicle
  supplies connector compatibility and peak charging kW; corridor stops are
  filtered by connector overlap inside `route_pitstops` and each stop's charge
  time is priced at `min(vehicle kW, station kW)`. An undeclared connector list
  or power figure is reported as unknown, never guessed.
- `/vehicles` — `GET`, `POST`, `GET /{id}`, `PATCH /{id}`,
  `POST /{id}/default`, `DELETE /{id}` for the signed-in driver's saved EVs,
  including `max_charging_kw` and `connector_compatibility`. Connector names
  are limited to CCS2, Type 2, CHAdeMO, Bharat AC, Bharat DC, and Tesla.
- `POST /bookings/lock`, `POST /bookings`, `GET /bookings`,
  `GET /bookings/{id}`, `POST /bookings/{id}/cancel`.
- `POST /payments/razorpay/webhook` — verifies Razorpay HMAC signature and
  transitions payment/booking only from the signed provider event.
- `/vendor/*` — authenticated owner portal endpoints for the signed-in user's
  vendor profile, dashboard, bookings, availability, services, and revenue.
  `POST` and `PATCH /vendor/services` accept `supported_connectors` (same six
  names as vehicles) and `max_power_kw`; an empty connector array means "not
  declared" and route search then skips the listing.
  These operations derive `owner_id` from the verified Supabase user and
  scope vendor resources in SQL; browser-supplied vendor IDs are not accepted.
- `GET /vendor/payout-status` — routing state for the owner's own business,
  produced by `payout_status_view`: `routing_enabled`, `ready_disabled`,
  `disabled`, `account_required`, `kyc_required`, `approval_required`,
  `rate_invalid`, or `profile_required`, with the effective rate and its
  source, the 300 bps retention floor, and the masked KYC block.
- `GET /vendor/payout-transfers?limit=&offset=` — the owner's own ledger rows,
  newest first; `limit` defaults to 25 and is capped at 100.
- `POST /vendor/kyc` — accepts a masked PAN, masked bank account, GSTIN, and a
  provider reference only. Raw PAN or account numbers and uploaded documents
  are not part of the contract and are never stored.
- `/notifications/*` — `GET /notifications?unread_only=&limit=&offset=`,
  `PATCH /notifications/{id}/read`, `POST /notifications/read-all`,
  `GET /notifications/push-status`, `PUT /notifications/push-token`, and
  `DELETE /notifications/push-token?token=`. All reads and writes are scoped to
  the verified subject. `PUT` takes `{"token":"…","platform":"android|ios|web"}`
  where the token must match `^[A-Za-z0-9_:=-]{16,512}$`, upserts one row per
  provider and token, and queues a background drain of up to five pending
  deliveries. `DELETE` returns 404 `PUSH_TOKEN_NOT_FOUND` when the caller has
  never registered that token. With no FCM project configured the dispatcher
  claims nothing and `GET /notifications/push-status` reports it disabled, so a
  client without a native push SDK still gets the in-app feed and Realtime.
- `GET /vendor/disputes`, `GET /vendor/disputes/{id}`, and
  `POST /vendor/disputes/{id}/messages` — vendor owners can view and respond to
  cases involving their business. They cannot change case status or financials.
- `POST /disputes` with `Idempotency-Key`, `GET /disputes`,
  `GET /disputes/{id}`, and `POST /disputes/{id}/messages` — customer reads are
  scoped to the verified Supabase subject. The server derives customer, vendor,
  and payment amount from an eligible booking; client party IDs and amount fields
  are rejected.

Vendor booking acknowledgement is separate from the payment-confirmed booking
state. `POST /vendor/bookings/{id}/accept` requires a captured payment whose
webhook signature was verified. `POST /vendor/bookings/{id}/complete` requires
that acknowledgement. Vendor messages on a dispute do not change its status and
cannot trigger a refund.

The browser vendor app sends bearer tokens to the API. Set
`VENDOR_PORTAL_ORIGIN` to the deployed portal origin to allow its CORS requests;
the default is `http://localhost:3000` for local development. Optional
`VENDOR_PORTAL_PREVIEW_ORIGINS` is a comma-separated exact HTTPS origin allowlist
for approved preview deployments. Configure it in the API environment that serves
the frontend (for this preview calling the production API, the API project's
Production environment). Do not use wildcards or reflect request origins. CORS
does not bypass bearer-token or admin authorization checks.

## Super Admin endpoints

The internal console uses `/admin/*`. Every request validates the bearer token
against Supabase Auth, then loads the administrator account and permissions
from protected `admin_users` and `admin_role_permissions` tables. Supabase
`user_metadata` or browser-provided role/admin IDs are not authorization data.

- `GET /admin/me`, `GET /admin/dashboard`, `GET /admin/analytics`
- `GET /admin/vendors`, `GET /admin/vendors/{id}`,
  `GET /admin/vendors/{id}/financials`, `GET /admin/vendors/{id}/availability`,
  `POST /admin/vendors/{id}/action`
- `GET /admin/vendor-onboarding`,
  `POST /admin/vendor-onboarding/{id}/action`
- `GET /admin/bookings`, `GET /admin/bookings/{id}`,
  `GET /admin/live-operations`
- `GET /admin/transactions`, `GET /admin/payouts` (`payouts:read`)
- `GET /admin/payout-transfers?vendor_id=&limit=&offset=` (`payouts:read`) —
  ledger rows across every vertical, newest first, with a settlement summary.
  The portal labels `planned` rows as not yet confirmed by the provider.
- `POST /admin/vendors/{id}/payout-routing` (`payouts:manage`) — sets the
  linked account, the routing switch, and the per-vendor rate override, and
  requires a reason. The server rejects a rate that would leave the platform
  below the 300 bps retention floor or above 5000 bps, and refuses to enable
  routing without a linked account. Every change writes an audit record.
- `POST /admin/vendors/{id}/kyc` (`vendor_onboarding:manage`) — records the
  verification decision with masked PAN, masked bank account, GSTIN, and
  reference only.
- `GET /admin/refunds`, `GET /admin/refunds/eligibility`,
  `POST /admin/refunds` with an `Idempotency-Key` header,
  `POST /admin/refunds/{id}/approve`, `POST /admin/refunds/{id}/reject`
- `GET/POST /admin/disputes`, `GET /admin/disputes/{id}`,
  `POST /admin/disputes/{id}/action`, `POST /admin/disputes/{id}/refund-request`
- `GET /admin/financial-diagnostics`
- `GET /admin/settings` — platform configuration snapshot, including the
  payout readiness state (`estimate_only`, `ready_disabled`, `incomplete`, or
  `routing_enabled`) and the number of vendors currently routable
- `GET /admin/audit-logs`, `GET /admin/roles`, `GET /admin/admin-users`,
  `PATCH /admin/admin-users/{user_id}`

Refund requests are validated and persisted as `requested`; a finance admin
must separately approve or reject them with a reason. Approval and its audit
event are recorded before the backend submits to Razorpay. An ambiguous timeout
is left in processing and is never retried automatically. Configure Razorpay to send
signed `refund.created`, `refund.processed`, and `refund.failed` events to
`POST /payments/razorpay/webhook`. An existing local idempotency key never
causes a second provider call. A database migration configures a 5% commission
for verified charging payments and snapshots the rate at capture. Completed
refunds reduce the commission and the displayed vendor settlement estimate.
Payout routing is implemented and ledgered: when `VENDOR_SETTLEMENT_ENABLED` is
on and the vendor is routable, the split is attached to the Razorpay order at
creation and stored as `planned`, and only a signature-verified transfer event
from `PayoutRepository.apply_transfer_event` advances it to processed, settled,
failed, or reversed. With the flag off — the default — no split is planned,
nothing is sent, and every payout figure in the portals remains an estimate.
The admin console does not change booking states directly.

Disputes follow `open → investigating/awaiting_customer/awaiting_vendor →
resolved/closed`. Customer and vendor messages and admin decisions append
immutable `dispute_events`; admin changes also append immutable
`admin_audit_logs`. A partial unique index allows one active dispute per
booking. Admin list filters cover status, vendor/customer IDs, date range,
amount range, and reason text.

Refund requests from disputes validate the dispute-to-booking relationship,
verified captured payment, active refunds, and remaining balance on the server.
Finance approval then reuses `/admin/refunds/{id}/approve` and the existing
`RefundService`; dispute code never calls Razorpay or changes payment, booking,
or payout amounts. Provider webhooks append refund completion/failure to the
linked case. `GET /admin/financial-diagnostics` reports inconsistent records
without repairing them. Payout checks now read the transfer ledger: each
`vendor_payout_transfers` row is joined against the order that carried it and
reported as `PAYOUT_ORDER_NOT_FOUND`, `PAYOUT_GROSS_MISMATCH`,
`PAYOUT_SPLIT_MISMATCH`, or `PAYOUT_TRANSFER_UNMATCHED`. A `planned` row is
never treated as proof that a vendor was paid.

Role assignments are seeded by the admin migration. Finance Admin alone (besides
Super Admin) can approve and submit refunds. Operations Admin cannot create or
approve refunds, Support Admin cannot perform finance actions, and administrator
role changes are restricted to Super Admin. The first Super Admin must be
provisioned through a trusted database session; no public bootstrap endpoint is
provided.

## Apply the dispute migration

Migration `202610020005_dispute_hardening.sql` extends migrations `001` through
`004`; this environment has not applied it to a Supabase project. Authenticate
and link the intended project, review the pending migrations, apply, and verify
the remote migration ledger:

```sh
supabase login
supabase link --project-ref <project-ref>
supabase db push --dry-run
supabase db push
supabase migration list --linked
```

Stop if `db push` fails. The new unique active-dispute index deliberately fails
if duplicate active disputes already exist. Reconcile such rows explicitly
before retrying; the migration does not silently delete or repair them. See the
[Supabase CLI `db push` reference](https://supabase.com/docs/reference/cli/supabase-db-push).

Migrations `202610290001` through `202610290004` add the charger capability
columns and the three-argument `route_pitstops` overload, the charging slot
window exclusion constraint, the payout ledger with its masked KYC columns and
the new `payouts:manage` permission (the read half, `payouts:read`, has existed
since the admin platform migration), and the push outbox with the
Realtime publication entries. Apply them in order, then run
`supabase/verify.sql` in a psql session against the same database — it raises
rather than warns when a required table, policy, index, function, grant, or
publication member is missing, so a clean run is a schema precondition, not
evidence that a booking or payment journey works.

## Integration and security notes

`DATABASE_URL` must point to the migrated Supabase PostgreSQL database (use its
transaction pooler for Vercel) and
`REDIS_URL` to Redis. PostgreSQL statements are parameterized; user profile
and booking queries include the JWT-derived subject explicitly. Use a
restricted database role where possible; never expose database or Supabase
service-role credentials to clients. `POST /bookings` creates a real Razorpay
order and therefore requires provider credentials. A booking stays `pending`
until a valid `payment.captured` webhook arrives. Configure Razorpay to send
`payment.captured` and `payment.failed` events to the webhook path above.
The handler validates the raw-body signature, provider order/payment IDs, the
internal booking/payment relationship, INR currency, and the stored amount in
paise before checking replay/state behavior. Repeated same-ID events are
idempotent; captured/refunded payments cannot regress on an older failure event.
See `docs/booking-flow.md` for the payment state transition notes.
Configure the same endpoint for `transfer.processed`, `transfer.settled`,
`transfer.failed`, and `transfer.reversed`. Those four signed events are the
only thing that moves a ledger row out of `planned`: a repeated event for a row
already in that state is echoed without a second write, an event naming another
provider transfer or a different amount is refused with 409, an illegal
transition is refused with 409, and an event for a payout row that does not
exist returns 404. Realtime `postgres_changes` streams are owner-scoped by
row-level security rather than by the client's filter alone, so a table keeps
its owner-read policy before it is added to `supabase_realtime`.

OpenStreetMap (OSRM), Supabase Auth, Razorpay, PostgreSQL, and Redis must be configured
for those integrations to work. Automated endpoint tests use test doubles and
do not prove connectivity or RLS behavior against a live Supabase project.

## Integration test preparation

Copy `.env.integration.example` to `.env.integration.local` and fill in a
dedicated Supabase PostgreSQL database, Redis instance, and Razorpay test-mode
credentials. Never use production Razorpay keys. Set `RUN_INTEGRATION_TESTS=1`
and run `pytest apps/api/tests/integration -v`; the tests are skipped by default
and never contact external services unless explicitly enabled. Every module reads
`.env.integration.local` through `tests/integration/db_gate.py`, which never
overrides a variable the shell already exported.

The database-backed checks skip when nothing answers `SUPABASE_DB_URL`, so a
laptop or CI job without a local Supabase reports skips rather than six schema
failures. A database that does answer is never skipped: wrong credentials or an
unapplied migration must fail the run.
