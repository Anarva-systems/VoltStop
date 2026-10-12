-- Realtime is a notification path, not an authorization boundary. Every event
-- remains subject to the table's existing SELECT grant and RLS policies.
-- The driver subscribes to owner-filtered bookings and public/owned pitstop
-- catalog rows; booking/payment mutations remain on the trusted API.
do $$
declare
  table_name text;
begin
  if not exists (
    select 1 from pg_catalog.pg_publication
    where pubname = 'supabase_realtime'
  ) then
    execute 'create publication supabase_realtime';
  end if;

  foreach table_name in array array[
    'bookings',
    'vendors',
    'vendor_services',
    'charging_slots'
  ] loop
    if to_regclass(format('%I.%I', 'public', table_name)) is not null
      and not exists (
        select 1 from pg_catalog.pg_publication_tables
        where pubname = 'supabase_realtime'
          and schemaname = 'public'
          and tablename = table_name
      ) then
      execute format(
        'alter publication supabase_realtime add table %I.%I',
        'public', table_name
      );
    end if;
  end loop;
end
$$;
