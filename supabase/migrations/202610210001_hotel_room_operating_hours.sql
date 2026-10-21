-- Hotel room-type operating hours. Additive migration; existing rows default to 24-hour operation.
alter table public.hotel_room_types
  add column if not exists is_open_24_hours boolean not null default true,
  add column if not exists operating_start_time time not null default '00:00',
  add column if not exists operating_end_time time not null default '23:59';

alter table public.hotel_room_types drop constraint if exists hotel_room_types_operating_hours_check;
alter table public.hotel_room_types add constraint hotel_room_types_operating_hours_check
  check (is_open_24_hours or operating_start_time <> operating_end_time);
