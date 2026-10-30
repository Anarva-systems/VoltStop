-- Charger capability specs, vehicle charging power, and a vehicle-aware corridor query.
-- Charging capability is declared once on vendor_services; slots keep referencing the
-- vendor plus their existing service_type, so no slot backfill or new foreign key is needed.

alter table public.driver_vehicles
  add column if not exists max_charging_kw numeric(6,2)
    check (max_charging_kw is null or max_charging_kw > 0);
comment on column public.driver_vehicles.max_charging_kw is
  'Peak DC intake the driver declares; null stays null so charge time is not invented.';

alter table public.vendor_services
  add column if not exists supported_connectors text[] not null default '{}',
  add column if not exists max_power_kw numeric(6,2)
    check (max_power_kw is null or max_power_kw > 0);

do $$ begin
  alter table public.vendor_services
    add constraint vendor_services_supported_connectors_check
    check (supported_connectors <@ array[
      'CCS2', 'Type 2', 'CHAdeMO', 'Bharat AC', 'Bharat DC', 'Tesla'
    ]::text[]);
exception when duplicate_object then null; end $$;

comment on column public.vendor_services.supported_connectors is
  'Connector plugs available at this service; an empty array means the vendor has not declared them.';
comment on column public.vendor_services.max_power_kw is
  'Highest delivered power at this service; null is surfaced as unknown, never guessed.';

-- Vehicle-aware corridor pit stops. Replaces the two-argument form so the route guard,
-- radius bound, and ordering stay in one place instead of being duplicated by callers.
-- Both signatures are dropped first: CREATE OR REPLACE cannot change the returned
-- column list (SQLSTATE 42P13), and a half-applied run may already hold the new form.
drop function if exists public.route_pitstops(jsonb, double precision);
drop function if exists public.route_pitstops(jsonb, double precision, text[]);

create or replace function public.route_pitstops(
  p_route_geojson jsonb,
  p_radius_km double precision default 15,
  p_connectors text[] default null
)
returns table (
  vendor jsonb,
  distance_km double precision,
  services jsonb,
  available_slots jsonb,
  route_progress double precision,
  charging jsonb,
  connector_match text
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
          'display_name', s.display_name, 'description', s.description,
          'supported_connectors', s.supported_connectors, 'max_power_kw', s.max_power_kw
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
      coalesce((
        select jsonb_agg(jsonb_build_object(
          'id', cs.id, 'service_type', cs.service_type,
          'supported_connectors', s.supported_connectors, 'max_power_kw', s.max_power_kw
        ) order by cs.slot_start_time)
        from public.charging_slots cs
        join public.vendor_services s
          on s.vendor_id = cs.vendor_id and s.service_type = cs.service_type and s.is_active
        where cs.vendor_id = v.id and cs.status = 'available'
          and cs.slot_end_time > now()
          and cs.service_type = 'charging'
      ), '[]'::jsonb) as charging,
      extensions.st_linelocatepoint(route_geom, v.location::extensions.geometry) as route_progress
    from public.vendors v
    where v.is_active and v.is_verified
      and extensions.st_dwithin(
        v.location, route_geom::extensions.geography, p_radius_km * 1000.0
      )
  ), matched as (
    select candidates.*,
      case
        when candidates.charging = '[]'::jsonb then 'none'
        when p_connectors is null or coalesce(array_length(p_connectors, 1), 0) = 0 then 'unfiltered'
        when exists (
          select 1 from jsonb_array_elements(candidates.charging) as charge_unit
          where coalesce(
            jsonb_array_length(charge_unit -> 'supported_connectors'), 0
          ) > 0
            and exists (
              select 1 from jsonb_array_elements_text(charge_unit -> 'supported_connectors') as listed
              where listed = any (p_connectors)
            )
        ) then 'exact'
        when exists (
          select 1 from jsonb_array_elements(candidates.charging) as charge_unit
          where coalesce(
            jsonb_array_length(charge_unit -> 'supported_connectors'), 0
          ) = 0
        ) then 'unknown'
        else 'mismatch'
      end as connector_match
    from candidates
  )
  select matched.vendor, matched.distance_km, matched.services,
         matched.available_slots, matched.route_progress, matched.charging,
         matched.connector_match
  from matched
  where matched.connector_match <> 'mismatch'
  -- Declared-compatible stops first, then unverified listings, then the rest of the corridor.
  order by
    case matched.connector_match
      when 'exact' then 0 when 'unknown' then 1 when 'unfiltered' then 2 else 3
    end,
    matched.route_progress,
    matched.distance_km
  limit 20;
end;
$$;

revoke all on function public.route_pitstops(jsonb, double precision, text[]) from public;
revoke all on function public.route_pitstops(jsonb, double precision, text[]) from anon;
grant execute on function public.route_pitstops(jsonb, double precision, text[]) to authenticated;

comment on function public.route_pitstops(jsonb, double precision, text[]) is
  'Vendors near a GeoJSON route ordered along it; p_connectors drops stops that declare no compatible plug.';

-- Publish the same charging facts on point-radius discovery so a driver can tell a
-- 60 kW CCS2 bay from an unverified listing before choosing where to stop.
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
        'id', s.id, 'service_type', s.service_type, 'price_inr', s.price_inr,
        'display_name', s.display_name, 'description', s.description,
        'supported_connectors', s.supported_connectors, 'max_power_kw', s.max_power_kw
      ) order by s.service_type)
      from public.vendor_services s
      where s.vendor_id = v.id and s.is_active
    ), '[]'::jsonb),
    coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', cs.id, 'slot_start_time', cs.slot_start_time,
        'slot_end_time', cs.slot_end_time, 'capacity', cs.capacity,
        'price_inr', cs.price_inr, 'service_type', cs.service_type
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
