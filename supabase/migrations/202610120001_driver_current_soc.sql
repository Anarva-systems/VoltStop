-- Persist the driver's current charge independently from a route request.
alter table public.profiles
  add column if not exists current_soc numeric(5,2)
  check (current_soc is null or current_soc between 0 and 100);

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'grant update (current_soc) on public.profiles to authenticated';
  end if;
end
$$;
