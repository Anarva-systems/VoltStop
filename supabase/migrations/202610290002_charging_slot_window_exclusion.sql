-- Availability windows are the unit of inventory: bookings reserve a charging_slots row up
-- to its capacity. Two overlapping rows for the same vendor and service therefore sell the
-- same bays or rooms twice, so the overlap itself has to be impossible at the database level.

create extension if not exists btree_gist with schema extensions;

-- The constraint is checked against rows that already exist, so report the duplicates
-- instead of letting ALTER TABLE fail with an opaque GiST error.
do $$
declare
  offenders text;
begin
  select string_agg(report, ' | ') into offenders
  from (
    select a.id || ' and ' || b.id || ' overlap (' || a.vendor_id || ', ' || a.service_type
           || ', ' || a.slot_start_time || ' to ' || b.slot_end_time || ')' as report
    from public.charging_slots a
    join public.charging_slots b
      on b.vendor_id = a.vendor_id
     and b.service_type = a.service_type
     and b.id > a.id
     and b.slot_start_time < a.slot_end_time
     and a.slot_start_time < b.slot_end_time
     and a.status <> 'closed'
     and b.status <> 'closed'
    limit 5
  ) duplicates;
  if offenders is not null then
    raise exception using errcode = '22023',
      message = 'Overlapping availability windows must be merged or closed before the '
                'exclusion constraint can be installed: ' || offenders;
  end if;
end $$;

-- Closed rows project to an empty range so a vendor can retire a window and re-open an
-- equivalent one without first deleting history.
--
-- The uuid and text equality opclasses come from btree_gist, which lives in the
-- extensions schema. They are named explicitly because an unqualified exclusion element
-- is resolved through search_path, and a session whose search_path omits 'extensions'
-- would otherwise fail with "no default operator class for access method gist".
alter table public.charging_slots
  add constraint charging_slots_no_overlapping_window
  exclude using gist (
    vendor_id extensions.uuid_ops with =,
    service_type extensions.text_ops with =,
    (case when status = 'closed' then '(empty)'::tstzrange
          else tstzrange(slot_start_time, slot_end_time, '[)') end) with &&
  );

comment on constraint charging_slots_no_overlapping_window on public.charging_slots is
  'One open availability window per vendor and service; capacity inside a window is the only way to sell more.';

insert into public.admin_permissions(permission_key, description) values
  ('operations:manage', 'Run availability and hold maintenance jobs')
on conflict (permission_key) do nothing;

insert into public.admin_role_permissions(role_name, permission_key) values
  ('SUPER_ADMIN', 'operations:manage'),
  ('OPERATIONS_ADMIN', 'operations:manage')
on conflict do nothing;
