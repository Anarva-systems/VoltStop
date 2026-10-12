-- Hotel room inventory is maintained per local calendar night. Reservations
-- atomically decrement every night in the requested stay.
create table public.hotel_room_types (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors(id) on delete cascade,
  name text not null check (length(trim(name)) between 2 and 100),
  description text check (description is null or length(description) <= 2000),
  max_guests integer not null check (max_guests between 1 and 12),
  base_rate_inr numeric(12,2) not null check (base_rate_inr > 0),
  total_rooms integer not null check (total_rooms between 1 and 10000),
  free_cancellation_hours integer not null default 24 check (free_cancellation_hours between 0 and 720),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, vendor_id)
);
create index hotel_room_types_vendor_active_idx on public.hotel_room_types(vendor_id, is_active);

create table public.hotel_room_inventory (
  room_type_id uuid not null references public.hotel_room_types(id) on delete cascade,
  stay_date date not null,
  room_capacity integer not null check (room_capacity between 0 and 10000),
  rooms_available integer not null check (rooms_available between 0 and room_capacity),
  nightly_rate_inr numeric(12,2) not null check (nightly_rate_inr > 0),
  updated_at timestamptz not null default now(),
  primary key (room_type_id, stay_date)
);

create table public.hotel_reservations (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid not null references public.profiles(id) on delete restrict,
  vendor_id uuid not null references public.vendors(id) on delete restrict,
  room_type_id uuid not null,
  check_in date not null,
  check_out date not null,
  guests integer not null check (guests between 1 and 12),
  rooms integer not null check (rooms between 1 and 4),
  amount_inr numeric(12,2) not null check (amount_inr > 0),
  free_cancellation_hours integer not null check (free_cancellation_hours between 0 and 720),
  currency char(3) not null default 'INR' check (currency = 'INR'),
  status text not null default 'payment_pending' check (status in (
    'payment_pending','confirmed','cancelled','expired','refund_pending','refund_failed','refunded'
  )),
  idempotency_key text not null,
  request_fingerprint text not null,
  hold_expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (room_type_id, vendor_id) references public.hotel_room_types(id, vendor_id) on delete restrict,
  check (check_out > check_in and check_out - check_in between 1 and 30),
  unique (customer_id, idempotency_key)
);
create index hotel_reservations_customer_idx on public.hotel_reservations(customer_id, created_at desc);
create index hotel_reservations_vendor_idx on public.hotel_reservations(vendor_id, status, created_at desc);
create index hotel_reservations_expiry_idx on public.hotel_reservations(hold_expires_at) where status='payment_pending';

create table public.hotel_reservation_nights (
  reservation_id uuid not null references public.hotel_reservations(id) on delete cascade,
  room_type_id uuid not null references public.hotel_room_types(id) on delete restrict,
  stay_date date not null,
  rooms integer not null check (rooms between 1 and 4),
  nightly_rate_inr numeric(12,2) not null check (nightly_rate_inr > 0),
  primary key (reservation_id, stay_date),
  foreign key (room_type_id, stay_date) references public.hotel_room_inventory(room_type_id, stay_date) on delete restrict
);

-- Separate payment subject preserves the existing charging booking/payment FK.
create table public.hotel_reservation_payments (
  id uuid primary key default gen_random_uuid(),
  reservation_id uuid not null unique references public.hotel_reservations(id) on delete restrict,
  razorpay_order_id text unique,
  razorpay_payment_id text unique,
  amount_inr numeric(12,2) not null check (amount_inr > 0),
  currency char(3) not null default 'INR' check (currency='INR'),
  status text not null default 'pending' check (status in ('pending','captured','failed','refunded')),
  webhook_verified boolean not null default false,
  order_state text not null default 'creating' check (order_state in ('creating','ready','reconciliation_required')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index hotel_payments_order_idx on public.hotel_reservation_payments(razorpay_order_id);

-- Customer cancellation/late capture refunds are reviewed and issued only by
-- a finance administrator; provider status is recorded separately.
create table public.hotel_refunds (
  id uuid primary key default gen_random_uuid(),
  reservation_id uuid not null references public.hotel_reservations(id) on delete restrict,
  payment_id uuid not null references public.hotel_reservation_payments(id) on delete restrict,
  amount_inr numeric(12,2) not null check (amount_inr > 0),
  reason text not null check (length(trim(reason)) > 0),
  status text not null default 'requested' check (status in ('requested','approved','processing','completed','failed','rejected')),
  idempotency_key text not null unique,
  razorpay_refund_id text unique,
  provider_status text,
  provider_error text,
  requested_by uuid not null references public.profiles(id) on delete restrict,
  approved_by uuid references public.profiles(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index hotel_refunds_status_idx on public.hotel_refunds(status, created_at desc);

alter table public.hotel_room_types enable row level security;
alter table public.hotel_room_inventory enable row level security;
alter table public.hotel_reservations enable row level security;
alter table public.hotel_reservation_nights enable row level security;
alter table public.hotel_reservation_payments enable row level security;
alter table public.hotel_refunds enable row level security;

create policy hotel_rooms_public_read on public.hotel_room_types for select to anon, authenticated
  using (is_active and exists(select 1 from public.vendors v where v.id=vendor_id and v.is_active and v.is_verified));
create policy hotel_rooms_owner_read on public.hotel_room_types for select to authenticated
  using (exists(select 1 from public.vendors v where v.id=vendor_id and v.owner_id=(select auth.uid())));
create policy hotel_inventory_public_read on public.hotel_room_inventory for select to anon, authenticated
  using (exists(select 1 from public.hotel_room_types r join public.vendors v on v.id=r.vendor_id
    where r.id=room_type_id and r.is_active and v.is_active and v.is_verified));
create policy hotel_inventory_owner_read on public.hotel_room_inventory for select to authenticated
  using (exists(select 1 from public.hotel_room_types r join public.vendors v on v.id=r.vendor_id
    where r.id=room_type_id and v.owner_id=(select auth.uid())));
create policy hotel_reservations_customer_read on public.hotel_reservations for select to authenticated
  using (customer_id=(select auth.uid()));
create policy hotel_reservations_vendor_read on public.hotel_reservations for select to authenticated
  using (exists(select 1 from public.vendors v where v.id=vendor_id and v.owner_id=(select auth.uid())));
create policy hotel_nights_owner_read on public.hotel_reservation_nights for select to authenticated
  using (exists(select 1 from public.hotel_reservations r join public.vendors v on v.id=r.vendor_id
    where r.id=reservation_id and (r.customer_id=(select auth.uid()) or v.owner_id=(select auth.uid()))));
create policy hotel_payments_owner_read on public.hotel_reservation_payments for select to authenticated
  using (exists(select 1 from public.hotel_reservations r join public.vendors v on v.id=r.vendor_id
    where r.id=reservation_id and (r.customer_id=(select auth.uid()) or v.owner_id=(select auth.uid()))));
create policy hotel_refunds_owner_read on public.hotel_refunds for select to authenticated
  using (requested_by=(select auth.uid()) or exists(select 1 from public.hotel_reservations r join public.vendors v on v.id=r.vendor_id
    where r.id=reservation_id and v.owner_id=(select auth.uid())) or (select public.is_platform_admin()));

grant select on public.hotel_room_types, public.hotel_room_inventory, public.hotel_reservations,
  public.hotel_reservation_nights, public.hotel_reservation_payments, public.hotel_refunds to authenticated;
grant select on public.hotel_room_types, public.hotel_room_inventory to anon;
