-- Apply after the hotel reservation migration. Existing room types remain bookable
-- with no new restriction; vendors can configure a daily window at any time.
alter table public.hotel_room_types
  add column is_open_24_hours boolean not null default true,
  add column operating_start_time time not null default '00:00',
  add column operating_end_time time not null default '23:59',
  add constraint hotel_room_types_hours_valid check (
    is_open_24_hours or operating_start_time <> operating_end_time
  );

alter table public.hotel_reservations
  add column check_in_time time not null default '14:00',
  add column check_out_time time not null default '11:00';
