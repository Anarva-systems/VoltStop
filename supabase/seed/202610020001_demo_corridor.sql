-- Development-only sample partner network on the Srikakulam–Vijayawada NH-16 corridor.
-- All businesses and coordinates are fictional/demo approximations, not verified partners.
insert into public.vendors
  (id, name, type, lat, lng, address, phone, description, is_active, is_verified)
values
  ('10000000-0000-4000-8000-000000000001', 'Demo Coastal Kitchen - Srikakulam', 'restaurant', 18.2969, 83.8971, 'Demo NH-16 service road, Srikakulam, Andhra Pradesh', '+91-90000-10001', 'Fictional highway restaurant with charging bays.', true, true),
  ('10000000-0000-4000-8000-000000000002', 'Demo Highway Dhaba - Vizianagaram', 'restaurant', 18.1133, 83.3970, 'Demo NH-16 corridor, Vizianagaram, Andhra Pradesh', '+91-90000-10002', 'Fictional dhaba serving travelers around the clock.', true, true),
  ('10000000-0000-4000-8000-000000000003', 'Demo Bay Rest Stop - Visakhapatnam', 'hotel', 17.6868, 83.2185, 'Demo NH-16 corridor, Visakhapatnam, Andhra Pradesh', '+91-90000-10003', 'Fictional hotel offering rest and overnight charging.', true, true),
  ('10000000-0000-4000-8000-000000000004', 'Demo Eastern Dhaba - Tuni', 'restaurant', 17.3590, 82.5460, 'Demo NH-16 service road, Tuni, Andhra Pradesh', '+91-90000-10004', 'Fictional highway dhaba with food and EV charging.', true, true),
  ('10000000-0000-4000-8000-000000000005', 'Demo Godavari Transit Hotel - Rajahmundry', 'hotel', 17.0005, 81.8040, 'Demo NH-16 corridor, Rajahmundry, Andhra Pradesh', '+91-90000-10005', 'Fictional transit hotel with overnight parking and charging.', true, true),
  ('10000000-0000-4000-8000-000000000006', 'Demo Green Mile Dhaba - Eluru', 'restaurant', 16.7107, 81.0952, 'Demo NH-16 service road, Eluru, Andhra Pradesh', '+91-90000-10006', 'Fictional stop for meals and short EV top-ups.', true, true),
  ('10000000-0000-4000-8000-000000000007', 'Demo Krishna Valley Inn - Vijayawada', 'hotel', 16.5062, 80.6480, 'Demo NH-16 corridor, Vijayawada, Andhra Pradesh', '+91-90000-10007', 'Fictional hotel with rest area and charging services.', true, true)
on conflict (id) do update set
  name = excluded.name, type = excluded.type, lat = excluded.lat, lng = excluded.lng,
  address = excluded.address, phone = excluded.phone, description = excluded.description,
  is_active = excluded.is_active, is_verified = excluded.is_verified;

insert into public.vendor_services (id, vendor_id, service_type, price_inr, is_active)
values
  ('20000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000001', 'food', 180, true),
  ('20000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000001', 'charging', 18, true),
  ('20000000-0000-4000-8000-000000000003', '10000000-0000-4000-8000-000000000002', 'food', 150, true),
  ('20000000-0000-4000-8000-000000000004', '10000000-0000-4000-8000-000000000002', 'charging', 20, true),
  ('20000000-0000-4000-8000-000000000005', '10000000-0000-4000-8000-000000000003', 'room', 2400, true),
  ('20000000-0000-4000-8000-000000000006', '10000000-0000-4000-8000-000000000003', 'sleep_and_charge', 2900, true),
  ('20000000-0000-4000-8000-000000000007', '10000000-0000-4000-8000-000000000003', 'parking', 100, true),
  ('20000000-0000-4000-8000-000000000008', '10000000-0000-4000-8000-000000000004', 'food', 160, true),
  ('20000000-0000-4000-8000-000000000009', '10000000-0000-4000-8000-000000000004', 'charging', 19, true),
  ('20000000-0000-4000-8000-000000000010', '10000000-0000-4000-8000-000000000005', 'room', 2800, true),
  ('20000000-0000-4000-8000-000000000011', '10000000-0000-4000-8000-000000000005', 'sleep_and_charge', 3400, true),
  ('20000000-0000-4000-8000-000000000012', '10000000-0000-4000-8000-000000000006', 'food', 140, true),
  ('20000000-0000-4000-8000-000000000013', '10000000-0000-4000-8000-000000000006', 'charging', 21, true),
  ('20000000-0000-4000-8000-000000000014', '10000000-0000-4000-8000-000000000007', 'room', 2600, true),
  ('20000000-0000-4000-8000-000000000015', '10000000-0000-4000-8000-000000000007', 'rest_area', 80, true),
  ('20000000-0000-4000-8000-000000000016', '10000000-0000-4000-8000-000000000007', 'charging', 20, true)
on conflict (id) do update set
  vendor_id = excluded.vendor_id, service_type = excluded.service_type,
  price_inr = excluded.price_inr, is_active = excluded.is_active;

insert into public.charging_slots
  (id, vendor_id, slot_start_time, slot_end_time, capacity, price_inr, status)
values
  ('30000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000001', date_trunc('day', now()) + interval '1 day 08 hours', date_trunc('day', now()) + interval '1 day 09 hours', 2, 450, 'available'),
  ('30000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000001', date_trunc('day', now()) + interval '1 day 09 hours', date_trunc('day', now()) + interval '1 day 10 hours', 3, 520, 'available'),
  ('30000000-0000-4000-8000-000000000003', '10000000-0000-4000-8000-000000000002', date_trunc('day', now()) + interval '1 day 10 hours', date_trunc('day', now()) + interval '1 day 11 hours', 1, 390, 'available'),
  ('30000000-0000-4000-8000-000000000004', '10000000-0000-4000-8000-000000000003', date_trunc('day', now()) + interval '1 day 12 hours', date_trunc('day', now()) + interval '1 day 14 hours', 4, 850, 'available'),
  ('30000000-0000-4000-8000-000000000005', '10000000-0000-4000-8000-000000000004', date_trunc('day', now()) + interval '1 day 15 hours', date_trunc('day', now()) + interval '1 day 16 hours', 2, 470, 'available'),
  ('30000000-0000-4000-8000-000000000006', '10000000-0000-4000-8000-000000000005', date_trunc('day', now()) + interval '1 day 18 hours', date_trunc('day', now()) + interval '1 day 20 hours', 3, 980, 'available'),
  ('30000000-0000-4000-8000-000000000007', '10000000-0000-4000-8000-000000000006', date_trunc('day', now()) + interval '1 day 08 hours', date_trunc('day', now()) + interval '1 day 09 hours', 1, 410, 'available'),
  ('30000000-0000-4000-8000-000000000008', '10000000-0000-4000-8000-000000000007', date_trunc('day', now()) + interval '1 day 10 hours', date_trunc('day', now()) + interval '1 day 11 hours', 5, 560, 'available')
on conflict (id) do update set
  vendor_id = excluded.vendor_id, slot_start_time = excluded.slot_start_time,
  slot_end_time = excluded.slot_end_time, capacity = excluded.capacity,
  price_inr = excluded.price_inr, status = excluded.status;
