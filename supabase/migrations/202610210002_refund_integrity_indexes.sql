-- Refund integrity indexes. Additive migration.
--
-- The application state machine allows at most one refund per payment that is
-- not failed or rejected: creation and approval paths check for existing open
-- refunds while holding the payment row lock. These partial unique indexes
-- enforce that invariant at the database level and serve payment-scoped
-- refund lookups (all such queries filter on these statuses). If existing
-- rows violate the invariant the index creation fails loudly; reconcile the
-- data before re-running.
create unique index if not exists refunds_payment_open_idx
  on public.refunds(payment_id) where status not in ('failed', 'rejected');

create unique index if not exists hotel_refunds_payment_open_idx
  on public.hotel_refunds(payment_id) where status not in ('failed', 'rejected');
