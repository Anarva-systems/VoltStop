-- Persisted pilot route plans required by POST /api/v1/routes/plan.
create table public.routes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  origin text not null check (length(trim(origin)) between 2 and 200),
  destination text not null check (length(trim(destination)) between 2 and 200),
  corridor text not null check (corridor = 'NH-16'),
  distance_meters integer not null check (distance_meters > 0),
  distance_source text not null check (length(trim(distance_source)) between 1 and 40),
  battery_kwh numeric(7,2) not null check (battery_kwh > 0 and battery_kwh <= 500),
  current_soc numeric(5,2) not null check (current_soc between 0 and 100),
  efficiency_km_per_kwh numeric(6,2) not null check (efficiency_km_per_kwh > 0 and efficiency_km_per_kwh <= 20),
  estimated_consumption_kwh numeric(8,2) not null check (estimated_consumption_kwh >= 0),
  estimated_remaining_soc numeric(7,2) not null,
  route_geojson jsonb not null check (jsonb_typeof(route_geojson) = 'object'),
  created_at timestamptz not null default now()
);

create index routes_user_created_idx on public.routes(user_id, created_at desc);
