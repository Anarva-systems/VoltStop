-- Run with psql against an already-available PostgreSQL database after applying
-- migrations. No Docker reset or service startup is required by this check.
-- Any failed assertion raises an exception and stops verification.
do $$
declare
  required_table text;
begin
  if not exists (select 1 from pg_extension where extname = 'postgis') then
    raise exception 'PostGIS extension is not enabled';
  end if;

  foreach required_table in array array[
    'profiles', 'vendors', 'vendor_services', 'charging_slots', 'bookings',
    'payments', 'booking_events', 'notifications', 'routes'
  ] loop
    if to_regclass(format('public.%I', required_table)) is null then
      raise exception 'Required table missing: %', required_table;
    end if;
    if not (select relrowsecurity from pg_class where oid = to_regclass(format('public.%I', required_table))) then
      raise exception 'RLS is not enabled on public.%', required_table;
    end if;
    if not exists (
      select 1 from pg_policies
      where schemaname = 'public' and tablename = required_table
    ) then
      raise exception 'No RLS policies found on public.%', required_table;
    end if;
  end loop;

  if not exists (
    select 1 from pg_catalog.pg_publication
    where pubname = 'supabase_realtime'
  ) then
    raise exception 'Supabase Realtime publication missing';
  end if;
  foreach required_table in array array[
    'bookings', 'vendors', 'vendor_services', 'charging_slots'
  ] loop
    if not exists (
      select 1 from pg_catalog.pg_publication_tables
      where pubname = 'supabase_realtime'
        and schemaname = 'public'
        and tablename = required_table
    ) then
      raise exception 'Realtime publication missing public.%', required_table;
    end if;
  end loop;

  if not exists (
    select 1 from pg_indexes
    where schemaname = 'public' and indexname = 'vendors_location_gix'
      and indexdef ilike '%using gist%'
  ) then
    raise exception 'Vendor location GiST index missing';
  end if;
  if not exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public' and p.proname = 'nearby_vendors') then
    raise exception 'nearby_vendors function missing';
  end if;
  if not exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public' and p.proname = 'route_pitstops') then
    raise exception 'route_pitstops function missing';
  end if;
  if has_table_privilege('anon', 'public.routes', 'select')
    or has_table_privilege('anon', 'public.routes', 'insert')
    or has_table_privilege('anon', 'public.routes', 'delete') then
    raise exception 'Anonymous users must not access driver route history';
  end if;
  if not has_table_privilege('authenticated', 'public.routes', 'select')
    or not has_any_column_privilege('authenticated', 'public.routes', 'insert') then
    raise exception 'Authenticated drivers need route-history select and insert grants';
  end if;
  if has_function_privilege('anon', 'public.route_pitstops(jsonb,double precision)', 'execute') then
    raise exception 'Anonymous users must not execute route_pitstops';
  end if;
  if has_function_privilege('anon', 'public.driver_has_vendor_booking(uuid)', 'execute') then
    raise exception 'Anonymous users must not execute the historical-vendor helper';
  end if;
  if not has_function_privilege('authenticated', 'public.driver_has_vendor_booking(uuid)', 'execute') then
    raise exception 'Authenticated drivers need the historical-vendor helper for booking history';
  end if;

  -- Exercise a geography distance query at the Srikakulam demo point.
  if not exists (
    select 1 from public.nearby_vendors(18.2969, 83.8971, 25) nv
    where nv.distance_km >= 0 and jsonb_typeof(nv.services) = 'array'
      and jsonb_typeof(nv.available_slots) = 'array'
  ) then
    raise exception 'Nearby-vendor spatial query returned no expected demo vendor';
  end if;

  -- Foreign key metadata check for critical ownership/resource relationships.
  if not exists (
    select 1 from pg_constraint c
    where c.conrelid = 'public.bookings'::regclass and c.contype = 'f'
  ) then
    raise exception 'Bookings foreign keys missing';
  end if;
end;
$$;

select extname, extversion from pg_extension where extname = 'postgis';
select tablename, rowsecurity from pg_tables where schemaname = 'public'
  and tablename in ('profiles', 'vendors', 'vendor_services', 'charging_slots', 'bookings', 'payments', 'booking_events', 'notifications', 'routes')
  order by tablename;
select indexname, indexdef from pg_indexes where schemaname = 'public'
  and tablename in ('vendors', 'charging_slots', 'bookings') order by tablename, indexname;
select vendor ->> 'name' as vendor_name, round(distance_km::numeric, 2) as distance_km,
       jsonb_array_length(services) as active_services,
       jsonb_array_length(available_slots) as slots
from public.nearby_vendors(18.2969, 83.8971, 200);
