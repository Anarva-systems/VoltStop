-- Driver-facing data can be read directly through Supabase with owner RLS.
-- Booking creation, slot locking, payment, and cancellation remain server-owned.

create or replace function public.is_valid_driver_route_geojson(payload jsonb)
returns boolean
language plpgsql
immutable
set search_path = ''
as $$
declare
  coordinates jsonb;
  coordinate jsonb;
  longitude double precision;
  latitude double precision;
begin
  if payload is null
    or jsonb_typeof(payload) <> 'object'
    or payload ->> 'type' <> 'LineString'
    or jsonb_typeof(payload -> 'coordinates') <> 'array'
    or octet_length(payload::text) > 524288 then
    return false;
  end if;

  coordinates := payload -> 'coordinates';
  if jsonb_array_length(coordinates) < 2
    or jsonb_array_length(coordinates) > 10000 then
    return false;
  end if;

  for coordinate in select value from jsonb_array_elements(coordinates) loop
    if jsonb_typeof(coordinate) <> 'array'
      or jsonb_array_length(coordinate) < 2
      or jsonb_array_length(coordinate) > 3
      or jsonb_typeof(coordinate -> 0) <> 'number'
      or jsonb_typeof(coordinate -> 1) <> 'number' then
      return false;
    end if;
    longitude := (coordinate ->> 0)::double precision;
    latitude := (coordinate ->> 1)::double precision;
    if longitude < -180 or longitude > 180
      or latitude < -90 or latitude > 90 then
      return false;
    end if;
    if jsonb_array_length(coordinate) = 3
      and jsonb_typeof(coordinate -> 2) <> 'number' then
      return false;
    end if;
  end loop;
  return true;
exception
  when invalid_text_representation or numeric_value_out_of_range then
    return false;
end;
$$;
revoke all on function public.is_valid_driver_route_geojson(jsonb) from public;
revoke all on function public.is_valid_driver_route_geojson(jsonb) from anon;
grant execute on function public.is_valid_driver_route_geojson(jsonb) to authenticated;

create table public.routes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid()
    references public.profiles(id) on delete cascade,
  origin text not null check (length(trim(origin)) between 2 and 100),
  destination text not null check (length(trim(destination)) between 2 and 100),
  corridor text not null default 'NH-16' check (corridor = 'NH-16'),
  distance_meters integer not null check (distance_meters > 0),
  distance_source text not null check (distance_source in ('openstreetmap', 'google_routes')),
  battery_kwh numeric(7,2) not null check (battery_kwh > 0 and battery_kwh <= 500),
  current_soc numeric(5,2) not null check (current_soc between 0 and 100),
  efficiency_km_per_kwh numeric(6,3) not null
    check (efficiency_km_per_kwh > 0 and efficiency_km_per_kwh <= 20),
  estimated_consumption_kwh numeric(9,2) not null check (estimated_consumption_kwh >= 0),
  estimated_remaining_soc numeric(7,2) not null check (estimated_remaining_soc <= 100),
  route_geojson jsonb not null check (public.is_valid_driver_route_geojson(route_geojson)),
  created_at timestamptz not null default now(),
  check (lower(trim(origin)) <> lower(trim(destination)) )
);
create index routes_user_created_idx on public.routes(user_id, created_at desc);

alter table public.routes enable row level security;
revoke all on public.routes from anon, authenticated;
grant select, delete on public.routes to authenticated;
grant insert (
  origin, destination, corridor, distance_meters, distance_source,
  battery_kwh, current_soc, efficiency_km_per_kwh,
  estimated_consumption_kwh, estimated_remaining_soc, route_geojson
) on public.routes to authenticated;

create policy routes_select_own on public.routes
  for select to authenticated
  using (user_id = (select auth.uid()));
create policy routes_insert_own on public.routes
  for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy routes_delete_own on public.routes
  for delete to authenticated
  using (user_id = (select auth.uid()));

-- Let a driver read the vendor and slot attached to their own historical booking,
-- even if that vendor/slot is no longer publicly available.
create or replace function public.driver_has_vendor_booking(p_vendor_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select (select auth.uid()) is not null and exists (
    select 1 from public.bookings b
    where b.vendor_id = p_vendor_id and b.user_id = (select auth.uid())
  );
$$;
revoke all on function public.driver_has_vendor_booking(uuid) from public;
revoke all on function public.driver_has_vendor_booking(uuid) from anon;
grant execute on function public.driver_has_vendor_booking(uuid) to authenticated;
comment on function public.driver_has_vendor_booking(uuid) is
  'Boolean owner check for historical vendor visibility, bound to auth.uid() and not a general booking lookup.';

create policy vendors_customer_booking_read on public.vendors
  for select to authenticated
  using ((select public.driver_has_vendor_booking(id)));
create policy charging_slots_customer_booking_read on public.charging_slots
  for select to authenticated
  using ((select public.driver_has_vendor_booking(vendor_id)) and exists (
    select 1 from public.bookings b
    where b.slot_id = charging_slots.id
      and b.vendor_id = charging_slots.vendor_id
      and b.user_id = (select auth.uid())
  ));

-- Match verified public partners to an OSRM LineString while respecting the
-- vendor/service/slot RLS policies. The result is ordered along the route.
create or replace function public.route_pitstops(
  p_route_geojson jsonb,
  p_radius_km double precision default 15
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
  route_geom extensions.geometry;
begin
  if not public.is_valid_driver_route_geojson(p_route_geojson) then
    raise exception using errcode = '22023', message = 'route_geojson must be a bounded geographic LineString';
  end if;
  if p_radius_km is null or p_radius_km <= 0 or p_radius_km > 50 then
    raise exception using errcode = '22023', message = 'p_radius_km must be greater than 0 and at most 50';
  end if;

  route_geom := extensions.st_setsrid(
    extensions.st_geomfromgeojson(p_route_geojson::text), 4326
  );
  if extensions.st_npoints(route_geom) < 2 then
    raise exception using errcode = '22023', message = 'route_geojson must contain at least two route points';
  end if;

  return query
  with candidates as (
    select
      jsonb_build_object(
        'id', v.id, 'name', v.name, 'type', v.type,
        'lat', v.lat, 'lng', v.lng, 'address', v.address,
        'description', v.description, 'image_url', v.image_url,
        'is_active', v.is_active, 'is_verified', v.is_verified
      ) as vendor,
      extensions.st_distance(v.location, route_geom::extensions.geography) / 1000.0 as distance_km,
      coalesce((
        select jsonb_agg(jsonb_build_object(
          'id', s.id, 'service_type', s.service_type, 'price_inr', s.price_inr,
          'display_name', s.display_name, 'description', s.description
        ) order by s.service_type)
        from public.vendor_services s
        where s.vendor_id = v.id and s.is_active
      ), '[]'::jsonb) as services,
      coalesce((
        select jsonb_agg(jsonb_build_object(
          'id', cs.id, 'slot_start_time', cs.slot_start_time,
          'slot_end_time', cs.slot_end_time, 'capacity', cs.capacity,
          'price_inr', cs.price_inr, 'service_type', cs.service_type
        ) order by cs.slot_start_time)
        from public.charging_slots cs
        where cs.vendor_id = v.id and cs.status = 'available'
          and cs.slot_end_time > now()
      ), '[]'::jsonb) as available_slots,
      extensions.st_linelocatepoint(route_geom, v.location::extensions.geometry) as route_progress
    from public.vendors v
    where v.is_active and v.is_verified
      and extensions.st_dwithin(
        v.location, route_geom::extensions.geography, p_radius_km * 1000.0
      )
  )
  select candidates.vendor, candidates.distance_km,
         candidates.services, candidates.available_slots
  from candidates
  order by candidates.route_progress, candidates.distance_km
  limit 20;
end;
$$;
revoke all on function public.route_pitstops(jsonb, double precision) from public;
revoke all on function public.route_pitstops(jsonb, double precision) from anon;
grant execute on function public.route_pitstops(jsonb, double precision) to authenticated;

comment on table public.routes is
  'Driver-owned route estimates and GeoJSON history; route values are approximate, non-financial client inputs.';
comment on function public.route_pitstops(jsonb, double precision) is
  'Returns active verified vendors near a GeoJSON route, ordered along it; SECURITY INVOKER preserves vendor RLS.';
