-- Vendor payout routing (Razorpay Route).
--
-- Deliberately NOT stored anywhere below: PAN, IFSC and bank account numbers.
-- Those belong to the payment provider, which is the party that verifies them.
-- The masked columns exist only so support can recognise an account on a call;
-- their checks require literal asterisks, so a full number cannot be saved here
-- even by mistake.

alter table public.vendors
  add column razorpay_linked_account_id text check (
    razorpay_linked_account_id is null or razorpay_linked_account_id ~ '^acc_[A-Za-z0-9]+$'
  ),
  add column payouts_enabled boolean not null default false,
  add column commission_rate_bps_override smallint check (
    commission_rate_bps_override is null or commission_rate_bps_override between 0 and 5000
  );

comment on column public.vendors.payouts_enabled is
  'Operator switch. Routing stays off until a person has checked the linked account and the KYC row.';
comment on column public.vendors.commission_rate_bps_override is
  'Per-vendor commission in basis points; null falls back to platform_commission_settings.rate_bps.';

alter table public.vendor_onboarding
  add column kyc_status text not null default 'not_started' check (
    kyc_status in ('not_started', 'submitted', 'under_review', 'verified', 'rejected')
  ),
  add column kyc_reference text check (
    kyc_reference is null or length(trim(kyc_reference)) between 4 and 120
  ),
  add column kyc_gstin text check (kyc_gstin is null or kyc_gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$'),
  add column kyc_pan_masked text check (kyc_pan_masked is null or kyc_pan_masked ~ '^[A-Z]{5}\*{4}[A-Z0-9]$'),
  add column bank_account_masked text check (bank_account_masked is null or bank_account_masked ~ '^\*{4,13}[0-9]{4}$'),
  add column kyc_verified_at timestamptz,
  add column kyc_verified_by uuid references auth.users(id) on delete set null,
  add constraint vendor_onboarding_kyc_verification_complete check (
    kyc_status <> 'verified' or (kyc_verified_at is not null and kyc_verified_by is not null)
  );

create table public.vendor_payout_transfers (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors(id) on delete restrict,
  source_kind text not null check (source_kind in ('charging_booking', 'hotel_reservation', 'restaurant_order')),
  source_reference_id uuid not null,
  razorpay_order_id text not null check (razorpay_order_id ~ '^order_[A-Za-z0-9]+$'),
  razorpay_transfer_id text unique check (
    razorpay_transfer_id is null or razorpay_transfer_id ~ '^trf_[A-Za-z0-9]+$'
  ),
  razorpay_payment_id text check (
    razorpay_payment_id is null or razorpay_payment_id ~ '^pay_[A-Za-z0-9]+$'
  ),
  currency text not null default 'INR' check (currency = 'INR'),
  gross_amount_inr numeric(12, 2) not null check (gross_amount_inr > 0),
  vendor_amount_inr numeric(12, 2) not null check (vendor_amount_inr > 0),
  commission_inr numeric(12, 2) not null check (commission_inr >= 0),
  rate_bps smallint not null check (rate_bps between 0 and 10000),
  status text not null default 'planned' check (
    status in ('planned', 'processed', 'settled', 'failed', 'reversed')
  ),
  failure_reason text,
  settlement_utr text,
  provider_event_at timestamptz,
  planned_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint vendor_payout_split_is_exhaustive check (
    round(gross_amount_inr - vendor_amount_inr - commission_inr, 2) = 0
  ),
  constraint vendor_payout_split_within_gross check (vendor_amount_inr < gross_amount_inr),
  constraint vendor_payout_failure_reason check (status <> 'failed' or failure_reason is not null),
  constraint vendor_payout_source_unique unique (razorpay_order_id, vendor_id)
);

create index vendor_payout_transfers_vendor_idx
  on public.vendor_payout_transfers (vendor_id, planned_at desc);
create index vendor_payout_transfers_status_idx
  on public.vendor_payout_transfers (status, planned_at desc);

create trigger vendor_payout_transfers_set_updated_at
  before update on public.vendor_payout_transfers
  for each row execute function public.set_updated_at();

comment on table public.vendor_payout_transfers is
  'One row per planned vendor transfer across charging, hotel and restaurant payments. '
  'A planned row is an instruction sent with the order, not money moved; only processed, '
  'settled and reversed statuses are written by verified provider events.';

insert into public.admin_permissions(permission_key, description) values
  ('payouts:manage', 'Enable payout routing and reconcile provider transfers')
on conflict (permission_key) do nothing;

insert into public.admin_role_permissions(role_name, permission_key) values
  ('SUPER_ADMIN', 'payouts:manage'),
  ('FINANCE_ADMIN', 'payouts:manage')
on conflict do nothing;

alter table public.vendor_payout_transfers enable row level security;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke all on public.vendor_payout_transfers from anon';
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'revoke all on public.vendor_payout_transfers from authenticated';
  end if;
end;
$$;

comment on column public.vendor_onboarding.kyc_pan_masked is
  'Display-only PAN mask, first five letters then four literal asterisks. '
  'The full PAN belongs to the payment provider and must never be written here; '
  'the check rejects any value without the asterisks.';
comment on column public.vendor_onboarding.bank_account_masked is
  'Display-only bank account mask, asterisks then the last four digits. '
  'The full number and IFSC stay with the payment provider; the check rejects '
  'a string that could hold a complete account number.';
comment on column public.vendor_onboarding.kyc_gstin is
  'GSTIN as published by the vendor, kept for the compliance record; it is a public '
  'identifier, not a secret, and its check enforces the 15-character format.';

-- Vendor routing is only usable when the destination and the review both agree.
create or replace function public.vendor_payout_destination(vendor_id uuid)
returns text
language sql
stable
security invoker
set search_path = ''
as $$
  select case
    when v.payouts_enabled
         and v.razorpay_linked_account_id is not null
         and o.kyc_status = 'verified'
         and o.status = 'approved'
    then v.razorpay_linked_account_id
  end
  from public.vendors v
  left join public.vendor_onboarding o on o.vendor_id = v.id
  where v.id = vendor_id;
$$;

revoke all on function public.vendor_payout_destination(uuid) from public;
grant execute on function public.vendor_payout_destination(uuid) to service_role;
