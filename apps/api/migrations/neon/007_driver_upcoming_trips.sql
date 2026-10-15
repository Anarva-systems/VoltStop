-- Driver-owned scheduled trips build on the existing route and vehicle models.
-- Passenger reservations, fares, seat allocation, and payments are deliberately
-- not introduced by this migration.
create table public.driver_trips (
  id uuid primary key default gen_random_uuid(),
  driver_id uuid not null references public.profiles(id) on delete cascade,
  vehicle_id uuid references public.driver_vehicles(id) on delete set null,
  route_id uuid references public.routes(id) on delete set null,
  origin text not null check (length(trim(origin)) between 2 and 100),
  destination text not null check (length(trim(destination)) between 2 and 100),
  departure_at timestamptz not null,
  estimated_arrival_at timestamptz,
  vehicle_make text not null check (length(trim(vehicle_make)) between 1 and 120),
  vehicle_model text not null check (length(trim(vehicle_model)) between 1 and 120),
  available_seats integer not null check (available_seats between 1 and 8),
  notes text check (notes is null or length(notes) <= 1000),
  is_discoverable boolean not null default false,
  status text not null default 'scheduled'
    check (status in ('scheduled', 'in_progress', 'completed', 'cancelled')),
  started_at timestamptz,
  completed_at timestamptz,
  cancelled_at timestamptz,
  idempotency_key text not null check (length(idempotency_key) between 8 and 200),
  request_fingerprint char(64) not null check (request_fingerprint ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (driver_id, idempotency_key),
  check (lower(trim(origin)) <> lower(trim(destination))),
  check (estimated_arrival_at is null or estimated_arrival_at > departure_at),
  check ((status in ('in_progress', 'completed')) = (started_at is not null)),
  check ((status = 'completed') = (completed_at is not null)),
  check ((status = 'cancelled') = (cancelled_at is not null))
);

create index driver_trips_driver_departure_idx
  on public.driver_trips(driver_id, departure_at, status);
create index driver_trips_discovery_idx
  on public.driver_trips(departure_at, lower(origin), lower(destination))
  where is_discoverable and status = 'scheduled';

create trigger driver_trips_set_updated_at
  before update on public.driver_trips
  for each row execute function public.set_updated_at();

comment on table public.driver_trips is
  'Driver-owned scheduled route plans. Discovery is read-only; passenger booking, fares, and seat allocation are not implemented.';
