-- Charging booking reliability: pending-hold expiry, idempotency replay, and
-- payment-order reconciliation state. Additive migration.
--
-- Existing rows keep their semantics: legacy payments already have provider
-- orders, so order_state defaults to 'ready'; new code writes 'creating'
-- explicitly before attaching the Razorpay order.
alter table public.bookings
  add column if not exists hold_expires_at timestamptz,
  add column if not exists idempotency_key text,
  add column if not exists request_fingerprint text;

alter table public.bookings drop constraint if exists bookings_idempotency_unique;
alter table public.bookings add constraint bookings_idempotency_unique unique (user_id, idempotency_key);
-- PostgreSQL treats NULLs as distinct in unique indexes, so legacy rows
-- without an idempotency key are unaffected.

create index if not exists bookings_expiry_idx
  on public.bookings(hold_expires_at) where status='pending' and hold_expires_at is not null;

alter table public.payments
  add column if not exists order_state text not null default 'ready';

alter table public.payments drop constraint if exists payments_order_state_check;
alter table public.payments add constraint payments_order_state_check
  check (order_state in ('creating','ready','reconciliation_required'));
