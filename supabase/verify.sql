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
    'bookings', 'vendors', 'vendor_services', 'charging_slots',
    'notifications', 'hotel_reservations', 'restaurant_orders'
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
  if has_function_privilege('anon', 'public.route_pitstops(jsonb,double precision,text[])', 'execute') then
    raise exception 'Anonymous users must not execute route_pitstops';
  end if;
  if has_table_privilege('anon', 'public.driver_vehicles', 'select') then
    raise exception 'Anonymous users must not read driver vehicles';
  end if;
  if not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'driver_vehicles'
      and column_name = 'max_charging_kw'
  ) then
    raise exception 'driver_vehicles.max_charging_kw is missing';
  end if;
  if not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'vendor_services'
      and column_name = 'supported_connectors'
  ) then
    raise exception 'vendor_services.supported_connectors is missing';
  end if;
  if not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'vendor_services'
      and column_name = 'max_power_kw'
  ) then
    raise exception 'vendor_services.max_power_kw is missing';
  end if;
  if not exists (
    select 1 from pg_constraint c
    join pg_class r on r.oid = c.conrelid
    where r.relname = 'vendor_services' and c.conname = 'vendor_services_supported_connectors_check'
  ) then
    raise exception 'vendor_services connector whitelist check is missing';
  end if;
  if not exists (select 1 from pg_extension where extname = 'btree_gist') then
    raise exception 'btree_gist is not enabled, so availability windows cannot be excluded';
  end if;
  if not exists (
    select 1 from pg_constraint c
    join pg_class r on r.oid = c.conrelid
    where r.relname = 'charging_slots' and c.contype = 'x'
      and c.conname = 'charging_slots_no_overlapping_window' and c.convalidated
  ) then
    raise exception 'charging_slots overlapping-window exclusion constraint is missing';
  end if;
  if not exists (
    select 1 from public.admin_permissions where permission_key = 'operations:manage'
  ) then
    raise exception 'operations:manage admin permission is missing';
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

-- A CCS2 vehicle must see CCS2 stops, and a Tesla-only vehicle must see strictly
-- fewer stops. That difference is what proves the connector filter removes rows
-- instead of merely labelling them.
do $$
declare
  corridor jsonb;
  ccs2_stops bigint;
  tesla_stops bigint;
begin
  corridor := jsonb_build_object('type', 'LineString', 'coordinates', jsonb_build_array(
    jsonb_build_array(83.8971, 18.2969), jsonb_build_array(80.6480, 16.5062)
  ));
  select count(*) into ccs2_stops from public.route_pitstops(corridor, 15, array['CCS2']);
  select count(*) into tesla_stops from public.route_pitstops(corridor, 15, array['Tesla']);
  if not exists (
    select 1 from public.route_pitstops(corridor, 15, array['CCS2'])
    where connector_match = 'exact'
  ) then
    raise exception 'route_pitstops returned no CCS2-compatible corridor stop';
  end if;
  if tesla_stops >= ccs2_stops then
    raise exception 'route_pitstops connector filter removed no incompatible stops';
  end if;
  if exists (
    select 1 from public.route_pitstops(corridor, 15, array['CCS2'])
    where connector_match = 'mismatch'
  ) then
    raise exception 'route_pitstops leaked an incompatible connector stop';
  end if;
end;
$$;

-- Push delivery must queue from SQL, stay private to the service role, and hang its
-- tokens off the profile that actually exists.
do $$
begin
  if to_regclass('public.user_push_tokens') is null or to_regclass('public.push_deliveries') is null then
    raise exception 'Push delivery tables are missing';
  end if;

  if not (select relrowsecurity from pg_class where oid = 'public.user_push_tokens'::regclass) then
    raise exception 'RLS is not enabled on public.user_push_tokens';
  end if;
  if has_table_privilege('anon', 'public.user_push_tokens', 'select')
     or has_table_privilege('authenticated', 'public.user_push_tokens', 'select')
     or has_table_privilege('authenticated', 'public.push_deliveries', 'select') then
    raise exception 'A client role can read push tokens or the delivery queue';
  end if;

  -- Whole-row assignment into a catalog %rowtype is rejected on PostgreSQL 18, so this
  -- check reads as an existence test like the rest of the file.
  if not exists (
    select 1 from pg_constraint c
    join pg_namespace n on n.oid = c.connamespace
     where n.nspname = 'public' and c.contype = 'f'
       and c.conrelid = 'public.user_push_tokens'::regclass
       and c.conname like 'user_push_tokens_user_id%'
       and c.confrelid = 'public.profiles'::regclass
  ) then
    raise exception 'user_push_tokens.user_id must reference public.profiles(id)';
  end if;

  if not exists (
    select 1 from information_schema.triggers
    where event_object_schema = 'public' and event_object_table = 'notifications'
      and action_statement like '%enqueue_push_delivery%'
  ) then
    raise exception 'Notifications do not enqueue a push delivery';
  end if;

  -- One queue row per notification keeps a replayed trigger from duplicating sends.
  if not exists (
    select 1 from pg_constraint c
    join pg_namespace n on n.oid = c.connamespace
    where n.nspname = 'public' and c.conrelid = 'public.push_deliveries'::regclass and c.contype = 'u'
      and array_length(c.conkey, 1) = 1
      and c.conkey[1] = (select attnum from pg_attribute
                         where attrelid = 'public.push_deliveries'::regclass and attname = 'notification_id')
  ) then
    raise exception 'push_deliveries.notification_id must be unique';
  end if;

  if exists (
    select 1 from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname = 'enqueue_push_delivery'
      and (p.prosecdef = false or p.proconfig is null
           or not exists (select 1 from unnest(p.proconfig) setting where setting like 'search_path=%'))
  ) then
    raise exception 'enqueue_push_delivery must be SECURITY DEFINER with a fixed search path';
  end if;
end;
$$;

-- Vendor payout routing must be ledgered, gated and unable to hold raw KYC secrets.
do $$
declare
  definition text;
begin
  if to_regclass('public.vendor_payout_transfers') is null then
    raise exception 'Required table missing: vendor_payout_transfers';
  end if;
  if not (select relrowsecurity from pg_class where oid = 'public.vendor_payout_transfers'::regclass) then
    raise exception 'RLS is not enabled on public.vendor_payout_transfers';
  end if;
  if has_table_privilege('anon', 'public.vendor_payout_transfers', 'select')
     or has_table_privilege('authenticated', 'public.vendor_payout_transfers', 'select') then
    raise exception 'Client roles must not read the vendor payout ledger';
  end if;

  foreach definition in array array[
    'vendor_payout_split_is_exhaustive', 'vendor_payout_split_within_gross',
    'vendor_payout_failure_reason', 'vendor_payout_source_unique'
  ] loop
    if not exists (
      select 1 from pg_constraint c
      where c.conrelid = 'public.vendor_payout_transfers'::regclass and c.conname = definition
    ) then
      raise exception 'Payout ledger constraint missing: %', definition;
    end if;
  end loop;

  -- The ledger carries its own rate so an old split still replays after an override changes.
  if not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'vendor_payout_transfers' and column_name = 'rate_bps'
  ) then
    raise exception 'Payout ledger must store the rate applied to each split';
  end if;

  if not exists (
    select 1 from pg_constraint c
    where c.conrelid = 'public.vendor_onboarding'::regclass
      and c.conname = 'vendor_onboarding_kyc_verification_complete'
  ) then
    raise exception 'KYC verification completeness constraint is missing';
  end if;

  -- Mask columns must reject a value that could hold a full document number.
  select pg_get_constraintdef(oid) into definition from pg_constraint
   where conrelid = 'public.vendor_onboarding'::regclass and conname like '%kyc_pan_masked%'
     and contype = 'c';
  if definition is null or position('*' in definition) = 0 then
    raise exception 'Masked PAN column must require literal asterisks';
  end if;
  if 'ABCDE1234F' ~ '^[A-Z]{5}\*{4}[A-Z0-9]$' then
    raise exception 'PAN mask pattern accepts an unmasked PAN';
  end if;
  if not ('ABCDE****F' ~ '^[A-Z]{5}\*{4}[A-Z0-9]$') then
    raise exception 'PAN mask pattern rejects a correctly masked PAN';
  end if;
  if '1234567890123' ~ '^\*{4,13}[0-9]{4}$' then
    raise exception 'Bank mask pattern accepts a full account number';
  end if;
  if not ('*****1111' ~ '^\*{4,13}[0-9]{4}$') then
    raise exception 'Bank mask pattern rejects a correctly masked account';
  end if;
  if 'ABCDE1234F1Z' ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$' then
    raise exception 'GSTIN pattern accepts a malformed GSTIN';
  end if;
  if not ('29ABCDE1234F1Z5' ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$') then
    raise exception 'GSTIN pattern rejects a real GSTIN';
  end if;

  if not exists (
    select 1 from public.admin_permissions where permission_key = 'payouts:manage'
  ) then
    raise exception 'payouts:manage permission is not seeded';
  end if;
  if not exists (
    select 1 from public.admin_role_permissions
    where role_name = 'FINANCE_ADMIN' and permission_key = 'payouts:manage'
  ) then
    raise exception 'FINANCE_ADMIN was not granted payouts:manage';
  end if;

  -- Routing cannot be switched on for a vendor that has no destination account.
  select pg_get_constraintdef(oid) into definition from pg_constraint
   where conrelid = 'public.vendors'::regclass and contype = 'c'
     and conname like '%razorpay_linked_account_id%';
  if definition is null or position('acc_' in definition) = 0 then
    raise exception 'Linked account column must validate the Razorpay account id format';
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
