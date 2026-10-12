-- VoltStop database foundation. Apply through Supabase migrations, not client SQL.
create extension if not exists pgcrypto with schema extensions;
create extension if not exists postgis with schema extensions;

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
create or replace function public.is_platform_admin()
returns boolean
language sql
stable
security invoker
set search_path = ''
as $$
  select coalesce(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'admin';
$$;

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  phone text,
  name text,
  car_model text,
  battery_kwh numeric(7,2) check (battery_kwh is null or battery_kwh > 0),
  default_efficiency_km_per_kwh numeric(6,3)
    check (default_efficiency_km_per_kwh is null or default_efficiency_km_per_kwh > 0),
  current_soc numeric(5,2) check (current_soc is null or current_soc between 0 and 100),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.create_profile_for_auth_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, phone, name)
  values (
    new.id,
    new.phone,
    coalesce(new.raw_user_meta_data ->> 'name', new.raw_user_meta_data ->> 'full_name')
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.create_profile_for_auth_user();

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
create or replace function public.protect_vendor_admin_fields()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if current_user in ('postgres', 'supabase_admin')
    or auth.role() = 'service_role'
    or (select public.is_platform_admin()) then
    return new;
  end if;

  if tg_op = 'INSERT' then
    if new.owner_id is distinct from (select auth.uid())
      or new.is_active or new.is_verified then
      raise exception using errcode = '42501', message = 'Vendors cannot assign ownership or self-activate/self-verify';
    end if;
  elsif new.owner_id is distinct from old.owner_id
    or new.is_active is distinct from old.is_active
    or new.is_verified is distinct from old.is_verified then
    raise exception using errcode = '42501', message = 'Only platform admins may change vendor ownership or verification state';
  end if;
  return new;
end;
$$;
create trigger vendors_protect_admin_fields
  before insert or update on public.vendors
  for each row execute function public.protect_vendor_admin_fields();

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

create or replace function public.protect_charging_slot_status()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  active_bookings bigint;
begin
  if current_user in ('postgres', 'supabase_admin')
    or auth.role() = 'service_role'
    or (select public.is_platform_admin()) then
    return new;
  end if;

  if tg_op = 'UPDATE' then
    if old.status in ('locked', 'booked') and new.status is distinct from old.status then
      raise exception using errcode = '42501', message = 'Only the API or an admin may release a locked/booked slot';
    end if;
    if new.capacity < old.capacity or (old.status = 'closed' and new.status = 'available') then
      select count(*) into active_bookings
      from public.bookings b
      where b.slot_id = old.id and b.status in ('pending', 'confirmed');
      if new.capacity < old.capacity and active_bookings >= new.capacity then
        raise exception using errcode = '23514', message = 'Capacity cannot be reduced to or below active bookings';
      end if;
      if old.status = 'closed' and new.status = 'available'
        and active_bookings >= new.capacity then
        raise exception using errcode = '23514', message = 'Slot cannot be reopened at full capacity';
      end if;
    end if;
  end if;
  return new;
end;
$$;
create trigger charging_slots_protect_status
  before insert or update on public.charging_slots
  for each row execute function public.protect_charging_slot_status();

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

create or replace function public.protect_notification_mutations()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if auth.role() = 'service_role' or (select public.is_platform_admin()) then
    if tg_op = 'DELETE' then return old; end if;
    return new;
  end if;

  if tg_op = 'UPDATE'
    and new.id is not distinct from old.id
    and new.user_id is not distinct from old.user_id
    and new.booking_id is not distinct from old.booking_id
    and new.type is not distinct from old.type
    and new.title is not distinct from old.title
    and new.message is not distinct from old.message
    and new.created_at is not distinct from old.created_at then
    return new;
  end if;
  raise exception using errcode = '42501', message = 'Only admins may create, delete, or edit notification content';
end;
$$;
create trigger notifications_protect_mutations
  before insert or update or delete on public.notifications
  for each row execute function public.protect_notification_mutations();

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

-- RLS: access is constrained to the signed-in owner, verified public data,
-- vendor ownership, or a trusted app_metadata admin claim.
alter table public.profiles enable row level security;
alter table public.vendors enable row level security;
alter table public.vendor_services enable row level security;
alter table public.charging_slots enable row level security;
alter table public.bookings enable row level security;
alter table public.payments enable row level security;
alter table public.booking_events enable row level security;
alter table public.notifications enable row level security;

create policy profiles_select_self_or_admin on public.profiles
  for select to authenticated
  using (id = (select auth.uid()) or (select public.is_platform_admin()));
create policy profiles_update_self on public.profiles
  for update to authenticated
  using (id = (select auth.uid()))
  with check (id = (select auth.uid()));
create policy profiles_admin_manage on public.profiles
  for all to authenticated
  using ((select public.is_platform_admin()))
  with check ((select public.is_platform_admin()));
-- Prevent clients from inserting/deleting profiles or modifying primary keys.
revoke insert, delete, update on public.profiles from anon, authenticated;
grant update (phone, name, car_model, battery_kwh, default_efficiency_km_per_kwh, current_soc)
  on public.profiles to authenticated;

create policy vendors_public_read on public.vendors
  for select to anon, authenticated
  using (is_active and is_verified);
create policy vendors_owner_read on public.vendors
  for select to authenticated
  using (owner_id = (select auth.uid()) or (select public.is_platform_admin()));
create policy vendors_admin_manage on public.vendors
  for all to authenticated
  using ((select public.is_platform_admin()))
  with check ((select public.is_platform_admin()));
create policy vendors_owner_insert on public.vendors
  for insert to authenticated
  with check (owner_id = (select auth.uid()) and not is_verified and not is_active);
create policy vendors_owner_update on public.vendors
  for update to authenticated
  using (owner_id = (select auth.uid()) or (select public.is_platform_admin()))
  with check (owner_id = (select auth.uid()) or (select public.is_platform_admin()));
create policy vendors_owner_delete on public.vendors
  for delete to authenticated
  using (owner_id = (select auth.uid()) or (select public.is_platform_admin()));
grant insert (owner_id, name, type, lat, lng, address, phone, description)
  on public.vendors to authenticated;
grant update (owner_id, name, type, lat, lng, address, phone, description, is_active, is_verified)
  on public.vendors to authenticated;

create policy vendor_services_public_read on public.vendor_services
  for select to anon, authenticated
  using (is_active and exists (
    select 1 from public.vendors v
    where v.id = vendor_id and v.is_active and v.is_verified
  ));
create policy vendor_services_owner_manage on public.vendor_services
  for all to authenticated
  using (exists (
    select 1 from public.vendors v
    where v.id = vendor_id and v.owner_id = (select auth.uid())
  ))
  with check (exists (
    select 1 from public.vendors v
    where v.id = vendor_id and v.owner_id = (select auth.uid())
  ));
create policy vendor_services_admin_manage on public.vendor_services
  for all to authenticated
  using ((select public.is_platform_admin()))
  with check ((select public.is_platform_admin()));

create policy charging_slots_public_available_read on public.charging_slots
  for select to anon, authenticated
  using (status = 'available' and exists (
    select 1 from public.vendors v
    where v.id = vendor_id and v.is_active and v.is_verified
  ));
create policy charging_slots_owner_read on public.charging_slots
  for select to authenticated
  using (exists (
    select 1 from public.vendors v
    where v.id = vendor_id and (v.owner_id = (select auth.uid()) or (select public.is_platform_admin()))
  ));
create policy charging_slots_owner_insert on public.charging_slots
  for insert to authenticated
  with check (
    status in ('available', 'closed') and exists (
      select 1 from public.vendors v
      where v.id = vendor_id and (v.owner_id = (select auth.uid()) or (select public.is_platform_admin()))
    )
  );
create policy charging_slots_owner_update on public.charging_slots
  for update to authenticated
  using (exists (
    select 1 from public.vendors v
    where v.id = vendor_id and (v.owner_id = (select auth.uid()) or (select public.is_platform_admin()))
  ))
  with check (
    status in ('available', 'closed') and exists (
      select 1 from public.vendors v
      where v.id = vendor_id and (v.owner_id = (select auth.uid()) or (select public.is_platform_admin()))
    )
  );
create policy charging_slots_owner_delete on public.charging_slots
  for delete to authenticated
  using (exists (
    select 1 from public.vendors v
    where v.id = vendor_id and (v.owner_id = (select auth.uid()) or (select public.is_platform_admin()))
  ));

create policy charging_slots_admin_manage on public.charging_slots
  for all to authenticated
  using ((select public.is_platform_admin()))
  with check ((select public.is_platform_admin()));

-- Booking, payment, event, and notification mutations are server-owned for
-- drivers/vendors; trusted admins may manage them through authenticated RLS.
create policy bookings_user_read on public.bookings
  for select to authenticated
  using (user_id = (select auth.uid()));
create policy bookings_vendor_read on public.bookings
  for select to authenticated
  using (exists (
    select 1 from public.vendors v
    where v.id = vendor_id and v.owner_id = (select auth.uid())
  ));
create policy bookings_admin_manage on public.bookings
  for all to authenticated
  using ((select public.is_platform_admin()))
  with check ((select public.is_platform_admin()));
create policy payments_booking_owner_read on public.payments
  for select to authenticated
  using (exists (
    select 1 from public.bookings b where b.id = booking_id
    and (b.user_id = (select auth.uid()) or exists (
      select 1 from public.vendors v where v.id = b.vendor_id and v.owner_id = (select auth.uid())
    ))
  ));
create policy payments_admin_manage on public.payments
  for all to authenticated
  using ((select public.is_platform_admin()))
  with check ((select public.is_platform_admin()));
create policy booking_events_booking_owner_read on public.booking_events
  for select to authenticated
  using (exists (
    select 1 from public.bookings b
    where b.id = booking_id and (b.user_id = (select auth.uid()) or exists (
      select 1 from public.vendors v where v.id = b.vendor_id and v.owner_id = (select auth.uid())
    ))
  ));
create policy booking_events_admin_manage on public.booking_events
  for all to authenticated
  using ((select public.is_platform_admin()))
  with check ((select public.is_platform_admin()));
create policy notifications_user_read on public.notifications
  for select to authenticated
  using (user_id = (select auth.uid()) or (select public.is_platform_admin()));
create policy notifications_user_mark_read on public.notifications
  for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));
create policy notifications_admin_manage on public.notifications
  for all to authenticated
  using ((select public.is_platform_admin()))
  with check ((select public.is_platform_admin()));

-- Explicit Data API grants: RLS remains the row-level authorization boundary.
grant select on public.profiles, public.vendors, public.vendor_services,
  public.charging_slots, public.bookings, public.payments,
  public.booking_events, public.notifications to authenticated;
grant select on public.vendors, public.vendor_services, public.charging_slots to anon;
grant insert, update, delete on public.vendors, public.vendor_services,
  public.charging_slots to authenticated;
grant insert, update, delete on public.bookings, public.payments,
  public.booking_events to authenticated;
grant insert, update, delete on public.notifications to authenticated;
grant update (read_at) on public.notifications to authenticated;

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
revoke all on function public.nearby_vendors(double precision, double precision, double precision) from public;
grant execute on function public.nearby_vendors(double precision, double precision, double precision) to anon, authenticated;

comment on table public.bookings is
  'Bookings are created/transitioned by the trusted API. Lock the charging_slots row and check capacity in one transaction when allocating bookings.';
comment on function public.nearby_vendors(double precision, double precision, double precision) is
  'Returns active verified vendors within radius_km, ordered by PostGIS geography distance; RLS remains in effect.';
