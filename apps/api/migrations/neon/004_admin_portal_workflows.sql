-- Bring the Neon development schema in line with the admin portal workflows.
-- Additive only: grants page access to the same roles as the Supabase migration
-- and creates the persisted support tables used by the existing API.

begin;

insert into public.admin_permissions(permission_key,description) values
  ('customers:read','View customer directory and authorized booking/support history'),
  ('availability:read','Inspect platform service availability and capacity'),
  ('services:read','View services published by businesses'),
  ('services:manage','Change publish state or base catalog price for vendor services'),
  ('pricing:read','View persisted service, slot, room, and menu prices'),
  ('support:read','View support tickets and customer/vendor messages'),
  ('support:manage','Reply to, assign, prioritize, and resolve support tickets'),
  ('notifications:read','View and manage own in-app notifications'),
  ('settings:read','View safe platform configuration status')
on conflict(permission_key) do nothing;

insert into public.admin_role_permissions(role_name,permission_key) values
  ('SUPER_ADMIN','customers:read'),('SUPER_ADMIN','availability:read'),
  ('SUPER_ADMIN','services:read'),('SUPER_ADMIN','services:manage'),
  ('SUPER_ADMIN','pricing:read'),('SUPER_ADMIN','support:read'),('SUPER_ADMIN','support:manage'),
  ('SUPER_ADMIN','settings:read'),('SUPER_ADMIN','notifications:read'),
  ('OPERATIONS_ADMIN','availability:read'),('OPERATIONS_ADMIN','services:read'),
  ('OPERATIONS_ADMIN','services:manage'),('OPERATIONS_ADMIN','pricing:read'),
  ('OPERATIONS_ADMIN','notifications:read'),
  ('FINANCE_ADMIN','pricing:read'),('FINANCE_ADMIN','notifications:read'),
  ('SUPPORT_ADMIN','customers:read'),('SUPPORT_ADMIN','support:read'),
  ('SUPPORT_ADMIN','support:manage'),('SUPPORT_ADMIN','notifications:read'),
  ('VENDOR_MANAGER','services:read'),('VENDOR_MANAGER','notifications:read')
on conflict do nothing;

alter table public.notifications add column if not exists source_key text;
create unique index if not exists notifications_source_key_unique
  on public.notifications(source_key);

create table if not exists public.support_tickets (
  id uuid primary key default gen_random_uuid(),
  requester_id uuid not null references public.profiles(id) on delete restrict,
  vendor_id uuid references public.vendors(id) on delete restrict,
  booking_id uuid references public.bookings(id) on delete restrict,
  category text not null check (category in ('account','booking','payment','technical','business','other')),
  subject text not null check (length(trim(subject)) between 4 and 160),
  status text not null default 'open' check (status in ('open','in_progress','waiting_on_customer','resolved','closed')),
  priority text not null default 'normal' check (priority in ('normal','high','urgent')),
  assigned_to uuid references public.admin_users(user_id) on delete set null,
  idempotency_key text not null unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  resolved_at timestamptz
);
create index if not exists support_tickets_requester_updated_idx
  on public.support_tickets(requester_id,updated_at desc);
create index if not exists support_tickets_vendor_updated_idx
  on public.support_tickets(vendor_id,updated_at desc);
create index if not exists support_tickets_status_priority_idx
  on public.support_tickets(status,priority,updated_at desc);

create table if not exists public.support_ticket_messages (
  id uuid primary key default gen_random_uuid(),
  ticket_id uuid not null references public.support_tickets(id) on delete restrict,
  sender_user_id uuid not null references public.profiles(id) on delete restrict,
  sender_role text not null check (sender_role in ('customer','vendor','admin')),
  body text not null check (length(trim(body)) between 2 and 4000),
  is_internal boolean not null default false,
  idempotency_key text not null unique,
  created_at timestamptz not null default now()
);
create index if not exists support_ticket_messages_ticket_created_idx
  on public.support_ticket_messages(ticket_id,created_at);

create table if not exists public.support_ticket_events (
  id uuid primary key default gen_random_uuid(),
  ticket_id uuid not null references public.support_tickets(id) on delete restrict,
  actor_user_id uuid references public.profiles(id) on delete set null,
  event_type text not null check (length(trim(event_type)) between 1 and 80),
  details jsonb not null default '{}'::jsonb check (jsonb_typeof(details)='object'),
  created_at timestamptz not null default now()
);
create index if not exists support_ticket_events_ticket_created_idx
  on public.support_ticket_events(ticket_id,created_at);

drop trigger if exists support_tickets_updated_at on public.support_tickets;
create trigger support_tickets_updated_at before update on public.support_tickets
  for each row execute function public.set_updated_at();

create or replace function public.prevent_support_history_mutation()
returns trigger language plpgsql set search_path='' as $$
begin
  raise exception using errcode='55000',message='Support history is append-only';
end;
$$;
drop trigger if exists support_messages_immutable on public.support_ticket_messages;
create trigger support_messages_immutable before update or delete on public.support_ticket_messages
  for each row execute function public.prevent_support_history_mutation();
drop trigger if exists support_events_immutable on public.support_ticket_events;
create trigger support_events_immutable before update or delete on public.support_ticket_events
  for each row execute function public.prevent_support_history_mutation();

commit;
