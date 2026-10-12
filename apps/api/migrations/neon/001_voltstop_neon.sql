-- VoltStop Neon application schema.
--
-- Supabase Auth remains the identity provider. The FastAPI service verifies
-- Supabase bearer tokens and enforces ownership/RBAC before using this Neon DB.
-- This migration intentionally omits Supabase Data API RLS policies and auth
-- schema FKs because Neon is the application database, not Supabase Postgres.

begin;

create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;
create extension if not exists postgis with schema extensions;

-- VoltStop database foundation. Apply through Supabase migrations, not client SQL.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- Roles for administrative policies are read from protected app_metadata claims.
-- A client-editable profile column is deliberately not used for authorization.

create table public.profiles (
  id uuid primary key,
  phone text,
  email text,
  name text,
  car_model text,
  battery_kwh numeric(7,2) check (battery_kwh is null or battery_kwh > 0),
  default_efficiency_km_per_kwh numeric(6,3)
    check (default_efficiency_km_per_kwh is null or default_efficiency_km_per_kwh > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);


create table public.vendors (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid references public.profiles(id) on delete set null,
  name text not null check (length(trim(name)) > 0),
  type text not null check (type in ('restaurant', 'hotel')),
  location extensions.geography(Point,4326) not null,
  lat double precision not null check (lat between -90 and 90),
  lng double precision not null check (lng between -180 and 180),
  address text not null,
  phone text,
  description text,
  is_active boolean not null default false,
  is_verified boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index vendors_location_gix on public.vendors using gist (location);
create index vendors_active_verified_idx on public.vendors (is_active, is_verified);
create index vendors_owner_id_idx on public.vendors (owner_id);

-- Keep geography and scalar coordinates consistent; lat/lng are canonical.

create or replace function public.sync_vendor_location()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.location := extensions.st_setsrid(
    extensions.st_makepoint(new.lng, new.lat), 4326
  )::extensions.geography;
  return new;
end;
$$;
create trigger vendors_sync_location
  before insert or update on public.vendors
  for each row execute function public.sync_vendor_location();

create table public.vendor_services (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors(id) on delete cascade,
  service_type text not null check (service_type in (
    'food', 'charging', 'sleep_and_charge', 'room', 'parking', 'rest_area'
  )),
  price_inr numeric(12,2) not null check (price_inr >= 0),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (vendor_id, service_type)
);
create index vendor_services_vendor_active_idx on public.vendor_services (vendor_id, is_active);

create table public.charging_slots (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors(id) on delete cascade,
  slot_start_time timestamptz not null,
  slot_end_time timestamptz not null,
  capacity integer not null check (capacity > 0),
  price_inr numeric(12,2) not null check (price_inr >= 0),
  status text not null default 'available'
    check (status in ('available', 'locked', 'booked', 'closed')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (slot_end_time > slot_start_time),
  unique (id, vendor_id)
);
create index charging_slots_vendor_time_idx on public.charging_slots (vendor_id, slot_start_time);
create index charging_slots_available_time_idx on public.charging_slots (slot_start_time)
  where status = 'available';


create table public.bookings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete restrict,
  vendor_id uuid not null references public.vendors(id) on delete restrict,
  slot_id uuid not null,
  payment_id uuid,
  amount_paid numeric(12,2) not null default 0 check (amount_paid >= 0),
  status text not null default 'pending'
    check (status in ('pending', 'confirmed', 'cancelled', 'completed', 'expired')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (slot_id, vendor_id)
    references public.charging_slots(id, vendor_id) on delete restrict,
  unique (id, payment_id)
);
create index bookings_user_created_idx on public.bookings (user_id, created_at desc);
create index bookings_vendor_status_created_idx on public.bookings (vendor_id, status, created_at desc);
create index bookings_slot_status_idx on public.bookings (slot_id, status);

create table public.payments (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid not null unique references public.bookings(id) on delete restrict,
  razorpay_order_id text unique,
  razorpay_payment_id text unique,
  amount_inr numeric(12,2) not null check (amount_inr >= 0),
  currency char(3) not null default 'INR' check (currency = 'INR'),
  status text not null default 'pending'
    check (status in ('pending', 'authorized', 'captured', 'failed', 'refunded')),
  webhook_verified boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, booking_id)
);
-- The pointer on bookings is deferred so a booking and its payment can be
-- created/linked atomically in one transaction. The composite key enforces
-- that the pointer cannot reference another booking's payment.
alter table public.bookings
  add constraint bookings_payment_id_fkey
  foreign key (payment_id, id)
  references public.payments(id, booking_id)
  deferrable initially deferred;
create index payments_status_created_idx on public.payments (status, created_at desc);

create table public.booking_events (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid not null references public.bookings(id) on delete cascade,
  event_type text not null check (event_type in (
    'created', 'slot_locked', 'payment_started', 'payment_success',
    'payment_failed', 'confirmed', 'cancelled', 'expired', 'completed'
  )),
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now()
);
create index booking_events_booking_created_idx on public.booking_events (booking_id, created_at);

create table public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  booking_id uuid references public.bookings(id) on delete set null,
  type text not null check (length(trim(type)) > 0),
  title text not null,
  message text not null,
  read_at timestamptz,
  created_at timestamptz not null default now()
);
create index notifications_user_unread_idx on public.notifications (user_id, created_at desc)
  where read_at is null;


-- Updated-at automation for mutable records.
create trigger profiles_updated_at before update on public.profiles
  for each row execute function public.set_updated_at();
create trigger vendors_updated_at before update on public.vendors
  for each row execute function public.set_updated_at();
create trigger vendor_services_updated_at before update on public.vendor_services
  for each row execute function public.set_updated_at();
create trigger charging_slots_updated_at before update on public.charging_slots
  for each row execute function public.set_updated_at();
create trigger bookings_updated_at before update on public.bookings
  for each row execute function public.set_updated_at();
create trigger payments_updated_at before update on public.payments
  for each row execute function public.set_updated_at();

-- Public, RLS-respecting nearby search. Coordinates are WGS84 degrees;
-- radius is bounded to prevent accidentally unbounded scans.
create or replace function public.nearby_vendors(
  latitude double precision,
  longitude double precision,
  radius_km double precision
)
returns table (
  vendor jsonb,
  distance_km double precision,
  services jsonb,
  available_slots jsonb
)
language plpgsql
stable
security invoker
set search_path = ''
as $$
declare
  origin extensions.geography;
begin
  if latitude is null or latitude < -90 or latitude > 90 then
    raise exception using errcode = '22023', message = 'latitude must be between -90 and 90';
  end if;
  if longitude is null or longitude < -180 or longitude > 180 then
    raise exception using errcode = '22023', message = 'longitude must be between -180 and 180';
  end if;
  if radius_km is null or radius_km <= 0 or radius_km > 200 then
    raise exception using errcode = '22023', message = 'radius_km must be greater than 0 and at most 200';
  end if;

  origin := extensions.st_setsrid(extensions.st_makepoint(longitude, latitude), 4326)::extensions.geography;
  return query
  select
    jsonb_build_object(
      'id', v.id, 'name', v.name, 'type', v.type, 'lat', v.lat, 'lng', v.lng,
      'address', v.address, 'phone', v.phone, 'description', v.description
    ),
    extensions.st_distance(v.location, origin) / 1000.0,
    coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', s.id, 'service_type', s.service_type, 'price_inr', s.price_inr
      ) order by s.service_type)
      from public.vendor_services s
      where s.vendor_id = v.id and s.is_active
    ), '[]'::jsonb),
    coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', cs.id, 'slot_start_time', cs.slot_start_time,
        'slot_end_time', cs.slot_end_time, 'capacity', cs.capacity,
        'price_inr', cs.price_inr
      ) order by cs.slot_start_time)
      from public.charging_slots cs
      where cs.vendor_id = v.id and cs.status = 'available'
        and cs.slot_end_time > now()
    ), '[]'::jsonb)
  from public.vendors v
  where v.is_active and v.is_verified
    and extensions.st_dwithin(v.location, origin, radius_km * 1000.0)
  order by extensions.st_distance(v.location, origin), v.id;
end;
$$;
comment on table public.bookings is
  'Bookings are created/transitioned by the trusted API. Lock the charging_slots row and check capacity in one transaction when allocating bookings.';
comment on function public.nearby_vendors(double precision, double precision, double precision) is
  'Returns active verified vendors within radius_km, ordered by PostGIS geography distance; RLS remains in effect.';


alter table public.vendors
  add column if not exists image_url text;

alter table public.vendors
  add constraint vendors_image_url_http_check
  check (image_url is null or image_url ~ '^https?://');


alter table public.vendors
  add column if not exists operating_hours text;

alter table public.vendor_services
  add column if not exists display_name text,
  add column if not exists description text,
  add column if not exists capacity integer check (capacity is null or capacity > 0),
  add column if not exists availability jsonb not null default '{}'::jsonb
    check (jsonb_typeof(availability) = 'object');

alter table public.charging_slots
  add column if not exists service_type text not null default 'charging'
    check (service_type in ('food', 'charging', 'sleep_and_charge', 'room', 'parking', 'rest_area', 'combo'));

alter table public.bookings
  add column if not exists vendor_acknowledgement text not null default 'pending'
    check (vendor_acknowledgement in ('pending', 'accepted'));

alter table public.booking_events
  drop constraint if exists booking_events_event_type_check;
alter table public.booking_events
  add constraint booking_events_event_type_check check (event_type in (
    'created', 'slot_locked', 'payment_started', 'payment_success',
    'payment_failed', 'confirmed', 'cancelled', 'expired', 'completed',
    'vendor_accepted', 'vendor_completed'
  ));




-- Internal administrator control plane. These tables are accessed only by the
-- trusted API database role; authenticated browser clients receive no grants.
create table public.admin_roles (
  name text primary key,
  description text not null
);

create table public.admin_permissions (
  permission_key text primary key,
  description text not null
);

create table public.admin_role_permissions (
  role_name text not null references public.admin_roles(name) on delete cascade,
  permission_key text not null references public.admin_permissions(permission_key) on delete cascade,
  primary key (role_name, permission_key)
);

create table public.admin_users (
  user_id uuid primary key references public.profiles(id) on delete restrict,
  role_name text not null references public.admin_roles(name),
  is_active boolean not null default true,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index admin_users_role_active_idx on public.admin_users(role_name, is_active);

insert into public.admin_roles(name, description) values
  ('SUPER_ADMIN', 'Full platform access and administrator management'),
  ('OPERATIONS_ADMIN', 'Vendor, booking, availability, and live operations'),
  ('FINANCE_ADMIN', 'Transactions, payouts, and refunds'),
  ('SUPPORT_ADMIN', 'Customer support, bookings, and disputes'),
  ('VENDOR_MANAGER', 'Vendor onboarding, profiles, and verification')
on conflict (name) do nothing;

insert into public.admin_permissions(permission_key, description) values
  ('dashboard:read', 'View platform overview'),
  ('analytics:read', 'View platform analytics'),
  ('vendors:read', 'View vendor profiles'),
  ('vendors:manage', 'Approve, suspend, and reactivate vendors'),
  ('vendor_financials:read', 'View vendor level financial summaries'),
  ('vendor_onboarding:manage', 'Review vendor applications'),
  ('bookings:read', 'Search and inspect bookings'),
  ('operations:read', 'View corridor operations'),
  ('transactions:read', 'View payment transactions'),
  ('payouts:read', 'View payout calculations'),
  ('refunds:read', 'View refund records'),
  ('refunds:create', 'Issue verified payment refunds'),
  ('refunds:approve', 'Approve and submit a requested refund'),
  ('disputes:read', 'View disputes'),
  ('disputes:manage', 'Investigate and resolve disputes'),
  ('audit:read', 'Inspect immutable audit history'),
  ('admin_users:manage', 'Assign administrator roles and access'),
  ('roles:read', 'View administrator role permissions')
on conflict (permission_key) do nothing;

insert into public.admin_role_permissions(role_name, permission_key)
select 'SUPER_ADMIN', permission_key from public.admin_permissions
on conflict do nothing;

insert into public.admin_role_permissions(role_name, permission_key) values
  ('OPERATIONS_ADMIN', 'dashboard:read'),
  ('OPERATIONS_ADMIN', 'vendors:read'),
  ('OPERATIONS_ADMIN', 'vendors:manage'),
  ('OPERATIONS_ADMIN', 'vendor_onboarding:manage'),
  ('OPERATIONS_ADMIN', 'bookings:read'),
  ('OPERATIONS_ADMIN', 'operations:read'),
  ('FINANCE_ADMIN', 'dashboard:read'),
  ('FINANCE_ADMIN', 'transactions:read'),
  ('FINANCE_ADMIN', 'vendor_financials:read'),
  ('FINANCE_ADMIN', 'payouts:read'),
  ('FINANCE_ADMIN', 'refunds:read'),
  ('FINANCE_ADMIN', 'refunds:create'),
  ('FINANCE_ADMIN', 'refunds:approve'),
  ('SUPPORT_ADMIN', 'dashboard:read'),
  ('SUPPORT_ADMIN', 'bookings:read'),
  ('SUPPORT_ADMIN', 'disputes:read'),
  ('SUPPORT_ADMIN', 'disputes:manage'),
  ('VENDOR_MANAGER', 'dashboard:read'),
  ('VENDOR_MANAGER', 'vendors:read'),
  ('VENDOR_MANAGER', 'vendors:manage'),
  ('VENDOR_MANAGER', 'vendor_onboarding:manage')
on conflict do nothing;

create table public.vendor_onboarding (
  vendor_id uuid primary key references public.vendors(id) on delete restrict,
  status text not null default 'pending'
    check (status in ('pending','under_review','changes_requested','approved','rejected','suspended')),
  current_stage text not null default 'application'
    check (current_stage in ('application','business_details','documents','location','banking','verification','approval')),
  completed_stages jsonb not null default '["application","business_details","location"]'::jsonb
    check (jsonb_typeof(completed_stages) = 'array'),
  document_references jsonb not null default '[]'::jsonb
    check (jsonb_typeof(document_references) = 'array'),
  decision_reason text,
  reviewed_by uuid references public.profiles(id) on delete set null,
  submitted_at timestamptz not null default now(),
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index vendor_onboarding_status_created_idx on public.vendor_onboarding(status, submitted_at desc);
insert into public.vendor_onboarding(vendor_id, status, current_stage)
select id, case when is_verified then 'approved' else 'pending' end,
       case when is_verified then 'approval' else 'application' end
from public.vendors on conflict (vendor_id) do nothing;

create or replace function public.initialize_vendor_onboarding()
returns trigger language plpgsql set search_path = '' as $$
begin
  insert into public.vendor_onboarding(vendor_id,status,current_stage)
  values(new.id,'pending','application')
  on conflict(vendor_id) do nothing;
  return new;
end;
$$;
create trigger vendors_initialize_onboarding after insert on public.vendors
  for each row execute function public.initialize_vendor_onboarding();

create table public.refunds (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid not null references public.bookings(id) on delete restrict,
  payment_id uuid not null references public.payments(id) on delete restrict,
  requested_by uuid not null references public.profiles(id) on delete restrict,
  approved_by uuid references public.profiles(id) on delete restrict,
  approved_at timestamptz,
  amount_inr numeric(12,2) not null check (amount_inr > 0),
  currency char(3) not null default 'INR' check (currency = 'INR'),
  reason text not null check (length(trim(reason)) > 0),
  status text not null default 'requested'
    check (status in ('requested','approved','processing','completed','failed','rejected')),
  idempotency_key text not null unique,
  razorpay_refund_id text unique,
  provider_status text,
  provider_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index refunds_booking_status_idx on public.refunds(booking_id, status, created_at desc);
create index refunds_created_idx on public.refunds(created_at desc);

create table public.disputes (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid not null references public.bookings(id) on delete restrict,
  reason text not null check (length(trim(reason)) > 0),
  description text not null check (length(trim(description)) > 0),
  status text not null default 'open'
    check (status in ('open','investigating','awaiting_customer','awaiting_vendor','resolved','closed')),
  evidence jsonb not null default '[]'::jsonb check (jsonb_typeof(evidence) = 'array'),
  resolution text,
  created_by uuid references public.profiles(id) on delete set null,
  assigned_to uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index disputes_status_created_idx on public.disputes(status, created_at desc);
create index disputes_booking_idx on public.disputes(booking_id);

create table public.dispute_events (
  id uuid primary key default gen_random_uuid(),
  dispute_id uuid not null references public.disputes(id) on delete restrict,
  actor_user_id uuid references public.profiles(id) on delete set null,
  event_type text not null,
  message text,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now()
);
create index dispute_events_dispute_created_idx on public.dispute_events(dispute_id, created_at);

create table public.admin_audit_logs (
  id uuid primary key default gen_random_uuid(),
  admin_user_id uuid not null references public.profiles(id) on delete restrict,
  role_name text not null,
  action text not null,
  entity_type text not null,
  entity_id text,
  reason text,
  before_state jsonb,
  after_state jsonb,
  request_metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(request_metadata) = 'object'),
  created_at timestamptz not null default now()
);
create index admin_audit_created_idx on public.admin_audit_logs(created_at desc);
create index admin_audit_entity_idx on public.admin_audit_logs(entity_type, entity_id, created_at desc);

create or replace function public.prevent_admin_audit_mutation()
returns trigger language plpgsql set search_path = '' as $$
begin
  raise exception using errcode = '55000', message = 'Admin audit records are immutable';
end;
$$;
create trigger admin_audit_immutable
  before update or delete on public.admin_audit_logs
  for each row execute function public.prevent_admin_audit_mutation();

create trigger admin_users_set_updated_at before update on public.admin_users
  for each row execute function public.set_updated_at();
create trigger vendor_onboarding_set_updated_at before update on public.vendor_onboarding
  for each row execute function public.set_updated_at();
create trigger refunds_set_updated_at before update on public.refunds
  for each row execute function public.set_updated_at();
create trigger disputes_set_updated_at before update on public.disputes
  for each row execute function public.set_updated_at();












-- Dispute lifecycle, scoped access, and financial linkage. Previous migrations
-- are intentionally immutable; this migration extends their schema in place.
alter table public.disputes
  add column customer_id uuid references public.profiles(id) on delete restrict,
  add column vendor_id uuid references public.vendors(id) on delete restrict,
  add column amount_inr numeric(12,2),
  add column resolved_at timestamptz,
  add column resolved_by uuid references public.profiles(id) on delete set null;

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
  add column actor_id uuid references public.profiles(id) on delete set null,
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


insert into public.admin_permissions(permission_key,description)
values ('financial_diagnostics:read','Run read-only financial consistency diagnostics')
on conflict (permission_key) do nothing;
insert into public.admin_role_permissions(role_name,permission_key)
values ('SUPER_ADMIN','financial_diagnostics:read'),('FINANCE_ADMIN','financial_diagnostics:read')
on conflict do nothing;


commit;
