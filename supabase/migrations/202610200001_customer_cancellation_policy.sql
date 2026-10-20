-- Customer cancellation policy v1. Additive migration; no existing payment rows are changed.
alter table public.bookings
  add column if not exists cancellation_fee_inr numeric(12,2) not null default 0 check (cancellation_fee_inr >= 0),
  add column if not exists refund_amount_inr numeric(12,2) not null default 0 check (refund_amount_inr >= 0),
  add column if not exists cancellation_policy_version text,
  add column if not exists cancelled_at timestamptz;

alter table public.hotel_reservations
  add column if not exists check_in_time time not null default '14:00',
  add column if not exists check_out_time time not null default '11:00',
  add column if not exists cancellation_fee_inr numeric(12,2) not null default 0 check (cancellation_fee_inr >= 0),
  add column if not exists refund_amount_inr numeric(12,2) not null default 0 check (refund_amount_inr >= 0),
  add column if not exists cancellation_policy_version text,
  add column if not exists cancelled_at timestamptz;

alter table public.hotel_reservations drop constraint if exists hotel_reservations_status_check;
alter table public.hotel_reservations add constraint hotel_reservations_status_check
  check (status in ('payment_pending','confirmed','cancelled','expired','refund_pending','refund_failed','refund_partial','refunded'));

create index if not exists bookings_cancelled_at_idx on public.bookings(cancelled_at desc) where cancelled_at is not null;
create index if not exists hotel_reservations_cancelled_at_idx on public.hotel_reservations(cancelled_at desc) where cancelled_at is not null;
