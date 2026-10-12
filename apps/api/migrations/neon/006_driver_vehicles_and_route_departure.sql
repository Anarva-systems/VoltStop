-- Owner-scoped EV garage. Legacy profile fields are retained and copied once below.
create table if not exists public.driver_vehicles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  make text not null check (length(trim(make)) between 1 and 120),
  model text not null check (length(trim(model)) between 1 and 120),
  vehicle_type text not null default 'car' check (vehicle_type in ('car','suv','motorcycle','other')),
  battery_kwh numeric(7,2) not null check (battery_kwh > 0 and battery_kwh <= 500),
  efficiency_km_per_kwh numeric(6,2) not null check (efficiency_km_per_kwh > 0 and efficiency_km_per_kwh <= 20),
  current_soc numeric(5,2) check (current_soc between 0 and 100),
  connector_compatibility text[] not null default '{}',
  is_default boolean not null default false,
  idempotency_key text not null check (length(idempotency_key) between 8 and 200),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, idempotency_key)
);
create unique index if not exists driver_vehicles_one_default_per_user
  on public.driver_vehicles(user_id) where is_default;
create index if not exists driver_vehicles_user_created_idx
  on public.driver_vehicles(user_id, created_at, id);

insert into public.driver_vehicles(
  user_id, make, model, vehicle_type, battery_kwh, efficiency_km_per_kwh, current_soc,
  is_default, idempotency_key
)
select p.id, 'Unspecified', p.car_model, 'car', p.battery_kwh,
       p.default_efficiency_km_per_kwh, p.current_soc, true,
       'legacy-profile-' || p.id::text
from public.profiles p
where nullif(trim(p.car_model), '') is not null
  and p.battery_kwh is not null and p.battery_kwh > 0
  and p.default_efficiency_km_per_kwh is not null and p.default_efficiency_km_per_kwh > 0
  and not exists (select 1 from public.driver_vehicles v where v.user_id=p.id);

alter table public.routes add column if not exists departure_at timestamptz;
