-- Global 5% commission for verified charging payments. Existing verified
-- captures are grandfathered at 0%; future captures snapshot the active rate.
create table public.platform_commission_settings (
  id smallint primary key default 1 check (id = 1),
  rate_bps smallint not null check (rate_bps between 0 and 10000),
  updated_at timestamptz not null default now()
);

insert into public.platform_commission_settings (id, rate_bps)
values (1, 500)
on conflict (id) do nothing;

create table public.payment_commission_ledger (
  payment_id uuid primary key,
  booking_id uuid not null,
  captured_amount_inr numeric(12,2) not null check (captured_amount_inr >= 0),
  rate_bps smallint not null check (rate_bps between 0 and 10000),
  recorded_at timestamptz not null default now(),
  foreign key (payment_id, booking_id)
    references public.payments(id, booking_id) on delete restrict
);
create index payment_commission_ledger_booking_idx
  on public.payment_commission_ledger (booking_id);

create or replace function public.record_payment_commission_on_capture()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  configured_rate smallint;
begin
  if new.status not in ('captured', 'refunded') or not new.webhook_verified then
    return new;
  end if;

  select rate_bps into configured_rate
  from public.platform_commission_settings
  where id = 1;

  if configured_rate is null then
    raise exception 'Platform commission rate is not configured';
  end if;

  insert into public.payment_commission_ledger (
    payment_id, booking_id, captured_amount_inr, rate_bps, recorded_at
  ) values (
    new.id, new.booking_id, new.amount_inr, configured_rate, now()
  ) on conflict (payment_id) do nothing;

  return new;
end;
$$;

create trigger payments_record_commission
  after insert or update of status, webhook_verified on public.payments
  for each row execute function public.record_payment_commission_on_capture();

insert into public.payment_commission_ledger (
  payment_id, booking_id, captured_amount_inr, rate_bps, recorded_at
)
select p.id, p.booking_id, p.amount_inr, 0, p.updated_at
from public.payments p
where p.status in ('captured', 'refunded')
  and p.webhook_verified
on conflict (payment_id) do nothing;

alter table public.platform_commission_settings enable row level security;
alter table public.payment_commission_ledger enable row level security;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke all on public.platform_commission_settings, public.payment_commission_ledger from anon';
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'revoke all on public.platform_commission_settings, public.payment_commission_ledger from authenticated';
  end if;
end;
$$;
