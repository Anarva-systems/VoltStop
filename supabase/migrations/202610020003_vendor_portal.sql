alter table public.vendors
  add column if not exists operating_hours text;

alter table public.vendor_services
  add column if not exists display_name text,
  add column if not exists description text,
  add column if not exists capacity integer check (capacity is null or capacity > 0),
  add column if not exists availability jsonb not null default '{}'::jsonb
    check (jsonb_typeof(availability) = 'object');

alter table public.charging_slots
  add column if not exists service_type text not null default 'charging'
    check (service_type in ('food', 'charging', 'sleep_and_charge', 'room', 'parking', 'rest_area', 'combo'));

alter table public.bookings
  add column if not exists vendor_acknowledgement text not null default 'pending'
    check (vendor_acknowledgement in ('pending', 'accepted'));

alter table public.booking_events
  drop constraint if exists booking_events_event_type_check;
alter table public.booking_events
  add constraint booking_events_event_type_check check (event_type in (
    'created', 'slot_locked', 'payment_started', 'payment_success',
    'payment_failed', 'confirmed', 'cancelled', 'expired', 'completed',
    'vendor_accepted', 'vendor_completed'
  ));


grant insert (owner_id, name, type, lat, lng, address, phone, description, image_url, operating_hours)
  on public.vendors to authenticated;
grant update (name, type, lat, lng, address, phone, description, image_url, operating_hours)
  on public.vendors to authenticated;
