-- Admin portal permissions, persisted support workflow, and in-app notifications.
-- All messages and state transitions are stored server-side; browser roles do not grant access.

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
  ('SUPER_ADMIN','pricing:read'),('SUPER_ADMIN','support:read'),('SUPER_ADMIN','support:manage'),('SUPER_ADMIN','settings:read'),
  ('SUPER_ADMIN','notifications:read'),
  ('OPERATIONS_ADMIN','availability:read'),('OPERATIONS_ADMIN','services:read'),('OPERATIONS_ADMIN','services:manage'),
  ('OPERATIONS_ADMIN','pricing:read'),
  ('OPERATIONS_ADMIN','notifications:read'),
  ('FINANCE_ADMIN','pricing:read'),
  ('FINANCE_ADMIN','notifications:read'),
  ('SUPPORT_ADMIN','customers:read'),('SUPPORT_ADMIN','support:read'),('SUPPORT_ADMIN','support:manage'),
  ('SUPPORT_ADMIN','notifications:read'),
  ('VENDOR_MANAGER','services:read'),('VENDOR_MANAGER','notifications:read')
on conflict do nothing;

alter table public.notifications add column if not exists source_key text;
create unique index if not exists notifications_source_key_unique on public.notifications(source_key);

create or replace function public.protect_notification_mutations()
returns trigger language plpgsql security invoker set search_path='' as $$
begin
  if current_user in ('postgres','supabase_admin','service_role')
    or auth.role()='service_role' or (select public.is_platform_admin()) then
    if tg_op='DELETE' then return old; end if;
    return new;
  end if;
  if tg_op='UPDATE'
    and new.id is not distinct from old.id
    and new.user_id is not distinct from old.user_id
    and new.booking_id is not distinct from old.booking_id
    and new.type is not distinct from old.type
    and new.title is not distinct from old.title
    and new.message is not distinct from old.message
    and new.source_key is not distinct from old.source_key
    and new.created_at is not distinct from old.created_at then
    return new;
  end if;
  raise exception using errcode='42501',message='Only admins may create, delete, or edit notification content';
end;
$$;

create table public.support_tickets (
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
create index support_tickets_requester_updated_idx on public.support_tickets(requester_id,updated_at desc);
create index support_tickets_vendor_updated_idx on public.support_tickets(vendor_id,updated_at desc);
create index support_tickets_status_priority_idx on public.support_tickets(status,priority,updated_at desc);

create table public.support_ticket_messages (
  id uuid primary key default gen_random_uuid(),
  ticket_id uuid not null references public.support_tickets(id) on delete restrict,
  sender_user_id uuid not null references public.profiles(id) on delete restrict,
  sender_role text not null check (sender_role in ('customer','vendor','admin')),
  body text not null check (length(trim(body)) between 2 and 4000),
  is_internal boolean not null default false,
  idempotency_key text not null unique,
  created_at timestamptz not null default now()
);
create index support_ticket_messages_ticket_created_idx on public.support_ticket_messages(ticket_id,created_at);

create table public.support_ticket_events (
  id uuid primary key default gen_random_uuid(),
  ticket_id uuid not null references public.support_tickets(id) on delete restrict,
  actor_user_id uuid references public.profiles(id) on delete set null,
  event_type text not null check (length(trim(event_type)) between 1 and 80),
  details jsonb not null default '{}'::jsonb check (jsonb_typeof(details)='object'),
  created_at timestamptz not null default now()
);
create index support_ticket_events_ticket_created_idx on public.support_ticket_events(ticket_id,created_at);
create trigger support_tickets_updated_at before update on public.support_tickets
  for each row execute function public.set_updated_at();

alter table public.support_tickets enable row level security;
alter table public.support_ticket_messages enable row level security;
alter table public.support_ticket_events enable row level security;
revoke all on public.support_tickets,public.support_ticket_messages,public.support_ticket_events from anon,authenticated;
grant all on public.support_tickets,public.support_ticket_messages,public.support_ticket_events to service_role;

create or replace function public.prevent_support_history_mutation()
returns trigger language plpgsql set search_path='' as $$
begin
  raise exception using errcode='55000',message='Support history is append-only';
end;
$$;
create trigger support_messages_immutable before update or delete on public.support_ticket_messages
  for each row execute function public.prevent_support_history_mutation();
create trigger support_events_immutable before update or delete on public.support_ticket_events
  for each row execute function public.prevent_support_history_mutation();

create or replace function public.notify_booking_event()
returns trigger language plpgsql security definer set search_path='' as $$
declare b record; label text;
begin
  if new.event_type not in ('confirmed','cancelled','expired','completed','payment_failed') then return new; end if;
  select bk.user_id,bk.vendor_id,v.owner_id,v.name into b
    from public.bookings bk join public.vendors v on v.id=bk.vendor_id where bk.id=new.booking_id;
  if not found then return new; end if;
  label := replace(new.event_type,'_',' ');
  insert into public.notifications(user_id,booking_id,type,title,message,source_key)
    values(b.user_id,new.booking_id,'booking_'||new.event_type,'Booking '||label,
      'Your booking '||left(new.booking_id::text,8)||' is '||label||'.','booking-event:'||new.id||':'||b.user_id)
    on conflict(source_key) do nothing;
  if b.owner_id is not null and b.owner_id<>b.user_id then
    insert into public.notifications(user_id,booking_id,type,title,message,source_key)
      values(b.owner_id,new.booking_id,'booking_'||new.event_type,'Booking '||label,
        'A booking at '||b.name||' is '||label||'.','booking-event:'||new.id||':'||b.owner_id)
      on conflict(source_key) do nothing;
  end if;
  return new;
end;
$$;
create trigger booking_event_notify after insert on public.booking_events
  for each row execute function public.notify_booking_event();

create or replace function public.notify_restaurant_order_event()
returns trigger language plpgsql security definer set search_path='' as $$
declare o record; label text;
begin
  select ro.customer_id,ro.vendor_id,v.owner_id,v.name into o
    from public.restaurant_orders ro join public.vendors v on v.id=ro.vendor_id where ro.id=new.order_id;
  if not found then return new; end if;
  label := replace(new.event_type,'_',' ');
  insert into public.notifications(user_id,type,title,message,source_key)
    values(o.customer_id,'restaurant_order','Restaurant order update',
      'Your order at '||o.name||': '||label||'.','restaurant-event:'||new.id||':'||o.customer_id)
    on conflict(source_key) do nothing;
  if o.owner_id is not null and o.owner_id<>o.customer_id then
    insert into public.notifications(user_id,type,title,message,source_key)
      values(o.owner_id,'restaurant_order','Restaurant order update',
        'Order at '||o.name||': '||label||'.','restaurant-event:'||new.id||':'||o.owner_id)
      on conflict(source_key) do nothing;
  end if;
  return new;
end;
$$;
create trigger restaurant_order_event_notify after insert on public.restaurant_order_events
  for each row execute function public.notify_restaurant_order_event();

create or replace function public.notify_hotel_reservation_status()
returns trigger language plpgsql security definer set search_path='' as $$
declare h record;
begin
  if tg_op='UPDATE' and new.status is not distinct from old.status then return new; end if;
  select v.owner_id,v.name into h from public.vendors v where v.id=new.vendor_id;
  insert into public.notifications(user_id,type,title,message,source_key)
    values(new.customer_id,'hotel_reservation','Hotel reservation update',
      'Your reservation at '||coalesce(h.name,'the hotel')||' is '||replace(new.status,'_',' ')||'.',
      'hotel-reservation:'||new.id||':'||new.status||':'||new.updated_at)
    on conflict(source_key) do nothing;
  if h.owner_id is not null and h.owner_id<>new.customer_id then
    insert into public.notifications(user_id,type,title,message,source_key)
      values(h.owner_id,'hotel_reservation','Hotel reservation update',
        'A reservation at '||h.name||' is '||replace(new.status,'_',' ')||'.',
        'hotel-reservation:'||new.id||':'||new.status||':'||new.updated_at||':'||h.owner_id)
      on conflict(source_key) do nothing;
  end if;
  return new;
end;
$$;
create trigger hotel_reservation_status_notify after insert or update on public.hotel_reservations
  for each row execute function public.notify_hotel_reservation_status();
