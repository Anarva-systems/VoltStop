-- Push delivery for the notifications that SQL triggers already write.
--
-- Two moving parts: the device tokens a user has registered, and an outbox row per
-- notification. The outbox is filled by a trigger, so a notification created inside
-- notify_booking_event() is queued without that function knowing about push at all.
-- The API drains the queue; nothing here calls a vendor SDK from SQL.

do $$
declare
  table_name text;
begin
  if not exists (
    select 1 from pg_catalog.pg_publication where pubname = 'supabase_realtime'
  ) then
    execute 'create publication supabase_realtime';
  end if;
  foreach table_name in array array['notifications', 'hotel_reservations', 'restaurant_orders'] loop
    if to_regclass(format('%I.%I', 'public', table_name)) is not null
      and not exists (
        select 1 from pg_catalog.pg_publication_tables
        where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = table_name
      ) then
      execute format('alter publication supabase_realtime add table %I.%I', 'public', table_name);
    end if;
  end loop;
end
$$;

-- A registration token belongs to a device, and a device can move between accounts.
create table if not exists public.user_push_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  provider text not null default 'fcm' check (provider in ('fcm')),
  token text not null check (token ~ '^[A-Za-z0-9_:=-]{16,512}$'),
  platform text not null check (platform in ('android', 'ios', 'web')),
  last_seen_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_push_tokens_per_device unique (provider, token)
);

create index user_push_tokens_user_idx on public.user_push_tokens (user_id, provider);

comment on table public.user_push_tokens is
  'Device push registration tokens kept per driver/vendor account. Rotation is expected: '
  'the same token re-registered by another account moves rows rather than duplicating them.';

-- One queue row per notification, claimed by the API with SELECT ... FOR UPDATE SKIP LOCKED.
create table if not exists public.push_deliveries (
  id uuid primary key default gen_random_uuid(),
  notification_id uuid not null references public.notifications(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  status text not null default 'pending' check (
    status in ('pending', 'sending', 'sent', 'failed', 'skipped')
  ),
  attempt_count smallint not null default 0 check (attempt_count between 0 and 12),
  last_error text,
  available_at timestamptz not null default now(),
  delivered_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint push_deliveries_one_row_per_notification unique (notification_id),
  constraint push_deliveries_sent_has_timestamp check (status <> 'sent' or delivered_at is not null),
  constraint push_deliveries_failure_reason check (status <> 'failed' or last_error is not null)
);

create index push_deliveries_claim_idx
  on public.push_deliveries (available_at)
  where status in ('pending', 'failed');

comment on table public.push_deliveries is
  'Outbox between the in-app notification feed and the push provider. A row is skipped when '
  'the account has no registered device, which is normal and not an error.';

create or replace function public.enqueue_push_delivery()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.push_deliveries(notification_id, user_id)
    values (new.id, new.user_id)
    on conflict (notification_id) do nothing;
  return new;
end;
$$;

create trigger notification_push_enqueue
  after insert on public.notifications
  for each row execute function public.enqueue_push_delivery();

create trigger user_push_tokens_set_updated_at
  before update on public.user_push_tokens
  for each row execute function public.set_updated_at();
create trigger push_deliveries_set_updated_at
  before update on public.push_deliveries
  for each row execute function public.set_updated_at();

-- Devices are registered through the API, which connects as service_role; the token
-- itself is a routing secret and must not be readable by any client role.
alter table public.user_push_tokens enable row level security;
alter table public.push_deliveries enable row level security;
revoke all on public.user_push_tokens, public.push_deliveries from anon, authenticated;
grant all on public.user_push_tokens, public.push_deliveries to service_role;
