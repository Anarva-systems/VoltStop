-- Dispute lifecycle, scoped access, and financial linkage. Previous migrations
-- are intentionally immutable; this migration extends their schema in place.
alter table public.disputes
  add column customer_id uuid references public.profiles(id) on delete restrict,
  add column vendor_id uuid references public.vendors(id) on delete restrict,
  add column amount_inr numeric(12,2),
  add column resolved_at timestamptz,
  add column resolved_by uuid references auth.users(id) on delete set null;

update public.disputes d
set customer_id=b.user_id,
    vendor_id=b.vendor_id,
    amount_inr=coalesce(p.amount_inr,b.amount_paid,0)
from public.bookings b
left join public.payments p on p.id=b.payment_id
where b.id=d.booking_id;

alter table public.disputes
  alter column customer_id set not null,
  alter column vendor_id set not null,
  alter column amount_inr set not null,
  add constraint disputes_amount_nonnegative check (amount_inr >= 0);

create index disputes_customer_created_idx on public.disputes(customer_id,created_at desc);
create index disputes_vendor_created_idx on public.disputes(vendor_id,created_at desc);
create index disputes_status_updated_idx on public.disputes(status,updated_at desc);
create index disputes_amount_idx on public.disputes(amount_inr);
create unique index disputes_one_open_per_booking_idx on public.disputes(booking_id)
  where status in ('open','investigating','awaiting_customer','awaiting_vendor');

alter table public.dispute_events
  add column actor_id uuid references auth.users(id) on delete set null,
  add column actor_type text,
  add column idempotency_key text;

update public.dispute_events e
set actor_id=e.actor_user_id,
    actor_type=case
      when exists(select 1 from public.admin_users a where a.user_id=e.actor_user_id) then 'admin'
      when exists(select 1 from public.disputes d where d.id=e.dispute_id and d.customer_id=e.actor_user_id) then 'customer'
      when exists(select 1 from public.disputes d join public.vendors v on v.id=d.vendor_id
                  where d.id=e.dispute_id and v.owner_id=e.actor_user_id) then 'vendor'
      else 'system'
    end,
    event_type=case e.event_type
      when 'opened' then 'created'
      when 'investigate' then 'status_changed'
      when 'await_customer' then 'status_changed'
      when 'await_vendor' then 'status_changed'
      when 'resolve' then 'resolved'
      when 'reject' then 'closed'
      when 'close' then 'closed'
      when 'note' then 'admin_note'
      else e.event_type
    end;

alter table public.dispute_events
  alter column actor_type set not null,
  add constraint dispute_events_actor_type_check check (actor_type in ('customer','vendor','admin','system')),
  add constraint dispute_events_type_check check (event_type in (
    'created','status_changed','customer_message','vendor_message','admin_note',
    'evidence_added','refund_requested','refund_approved','refund_rejected','refund_submitted',
    'refund_completed','refund_failed','resolved','closed'
  ));
create unique index dispute_events_idempotency_idx on public.dispute_events(idempotency_key)
  where idempotency_key is not null;
create index dispute_events_actor_created_idx on public.dispute_events(actor_id,created_at desc);

create or replace function public.prevent_dispute_event_mutation()
returns trigger language plpgsql set search_path = '' as $$
begin
  raise exception using errcode = '55000', message = 'Dispute events are immutable';
end;
$$;
create trigger dispute_events_immutable
  before update or delete on public.dispute_events
  for each row execute function public.prevent_dispute_event_mutation();

alter table public.refunds add column dispute_id uuid references public.disputes(id) on delete restrict;
create index refunds_dispute_idx on public.refunds(dispute_id,created_at desc) where dispute_id is not null;

-- The authenticated clients only access disputes through the API, which applies
-- the verified JWT subject or vendor owner ID to every query.
alter table public.disputes enable row level security;
alter table public.dispute_events enable row level security;
revoke all on public.disputes, public.dispute_events from anon, authenticated;

insert into public.admin_permissions(permission_key,description)
values ('financial_diagnostics:read','Run read-only financial consistency diagnostics')
on conflict (permission_key) do nothing;
insert into public.admin_role_permissions(role_name,permission_key)
values ('SUPER_ADMIN','financial_diagnostics:read'),('FINANCE_ADMIN','financial_diagnostics:read')
on conflict do nothing;
