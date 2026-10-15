# Architecture

VoltStop is a modular monorepo with three clients/services and Supabase as the
system of record. The pilot is the Srikakulam ⇄ Vijayawada NH-16 corridor.

- `apps/mobile`: Flutter driver client. Feature-based boundaries are reserved
  for auth, journey planning, pitstops, bookings, payments, and profile.
- `apps/vendor-web`: desktop-first, responsive Next.js App Router vendor shell.
- `apps/api`: FastAPI boundary for versioned platform APIs and trusted
  provider/database operations, organized by auth, bookings, vendors, admin,
  disputes, finance diagnostics, and payment services.
- `supabase`: SQL migrations and local Supabase configuration.
- `packages`: reserved for dependency-light contracts/config/shared logic.
- Redis is intended for short-lived booking concurrency coordination, not as
  the booking system of record.

Clients call `/api/v1/`. FastAPI validates bearer tokens through Supabase
Auth and derives the subject from the validated user response. Its asyncpg
repository parameterizes SQL and scopes profile and booking queries to that
subject; deploy with a restricted database role where possible. Redis provides
owner-bound expiring booking locks, PostgreSQL row locks/capacity checks remain
authoritative, and Razorpay webhooks—not client callbacks—transition payments
and confirm bookings. OpenStreetMap (OSRM) is behind a provider interface and is
used for distance estimates.

Customer disputes are scoped by the verified user ID; vendor dispute reads and
responses are scoped by the owner-to-vendor relationship. Disputes keep booking-
derived customer/vendor/amount values and append-only event timelines. Admin
dispute decisions also use the protected role-permission matrix and immutable
admin audit log. Dispute refund requests link to existing refund records and
reuse the existing Razorpay refund service after Finance/Super Admin approval.
No dispute endpoint modifies booking, payment, refund, or payout amounts.

Read-only financial diagnostics report booking/payment/refund inconsistencies
without repair. Payment commission snapshots support calculated settlement
estimates, while payout consistency and transfer reconciliation remain
unavailable until a payout ledger is implemented. Integration test preparation
is in `apps/api/tests/integration`
and uses opt-in environment variables in `.env.integration.example`.

Never expose database, service-role, payment-secret, or webhook-secret
credentials to clients. Provider integration and endpoint tests do not replace
live Supabase RLS/database, Redis, payment sandbox, webhook, or routing
verification. Notifications, QR validation, automatic pending-order expiry,
evidence file storage, a payout ledger, and production observability/deployment
remain future work.
