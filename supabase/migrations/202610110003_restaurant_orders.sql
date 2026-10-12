-- Restaurant pickup orders with immutable price snapshots and provider-confirmed payments.
create table public.restaurant_menu_categories (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors(id) on delete cascade,
  name text not null check (length(trim(name)) between 2 and 80),
  sort_order integer not null default 0 check (sort_order between 0 and 10000),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, vendor_id)
);
create unique index restaurant_menu_category_name_idx on public.restaurant_menu_categories(vendor_id, lower(name));

create table public.restaurant_menu_items (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors(id) on delete cascade,
  category_id uuid not null,
  name text not null check (length(trim(name)) between 2 and 120),
  description text check (description is null or length(description) <= 1000),
  price_inr numeric(12,2) not null check (price_inr > 0),
  is_available boolean not null default true,
  options jsonb not null default '[]'::jsonb check (jsonb_typeof(options) = 'array'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (category_id, vendor_id) references public.restaurant_menu_categories(id, vendor_id) on delete restrict,
  unique (id, vendor_id)
);
create index restaurant_menu_items_vendor_idx on public.restaurant_menu_items(vendor_id, category_id, is_available);

create table public.restaurant_orders (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid not null references public.profiles(id) on delete restrict,
  vendor_id uuid not null references public.vendors(id) on delete restrict,
  status text not null default 'payment_pending' check (status in (
    'payment_pending','placed','accepted','preparing','ready','completed','payment_failed','payment_expired','cancelled','refund_review_required'
  )),
  fulfillment_method text not null default 'pickup' check (fulfillment_method = 'pickup'),
  total_inr numeric(12,2) not null check (total_inr > 0),
  currency char(3) not null default 'INR' check (currency = 'INR'),
  idempotency_key text not null,
  request_fingerprint text not null,
  payment_expires_at timestamptz not null default (now() + interval '15 minutes'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (customer_id, idempotency_key)
);
create index restaurant_orders_vendor_status_idx on public.restaurant_orders(vendor_id, status, created_at desc);
create index restaurant_orders_customer_idx on public.restaurant_orders(customer_id, created_at desc);

create table public.restaurant_order_items (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.restaurant_orders(id) on delete cascade,
  item_id uuid references public.restaurant_menu_items(id) on delete set null,
  item_name text not null,
  description_snapshot text,
  unit_price_inr numeric(12,2) not null check (unit_price_inr > 0),
  quantity integer not null check (quantity between 1 and 20),
  selected_options jsonb not null default '[]'::jsonb check (jsonb_typeof(selected_options) = 'array'),
  line_total_inr numeric(12,2) not null check (line_total_inr > 0),
  created_at timestamptz not null default now()
);
create index restaurant_order_items_order_idx on public.restaurant_order_items(order_id);

create table public.restaurant_order_payments (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null unique references public.restaurant_orders(id) on delete restrict,
  razorpay_order_id text unique,
  razorpay_payment_id text unique,
  amount_inr numeric(12,2) not null check (amount_inr > 0),
  currency char(3) not null default 'INR' check (currency = 'INR'),
  status text not null default 'pending' check (status in ('pending','captured','failed','refunded')),
  webhook_verified boolean not null default false,
  order_state text not null default 'creating' check (order_state in ('creating','ready','reconciliation_required')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index restaurant_order_payments_order_idx on public.restaurant_order_payments(razorpay_order_id);

create table public.restaurant_order_events (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.restaurant_orders(id) on delete cascade,
  event_type text not null check (length(trim(event_type)) between 1 and 80),
  actor_id uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now()
);
create index restaurant_order_events_order_idx on public.restaurant_order_events(order_id, created_at desc);

alter table public.restaurant_menu_categories enable row level security;
alter table public.restaurant_menu_items enable row level security;
alter table public.restaurant_orders enable row level security;
alter table public.restaurant_order_items enable row level security;
alter table public.restaurant_order_payments enable row level security;
alter table public.restaurant_order_events enable row level security;

create policy restaurant_categories_public_read on public.restaurant_menu_categories for select to anon, authenticated
  using (is_active and exists(select 1 from public.vendors v where v.id=vendor_id and v.type='restaurant' and v.is_active and v.is_verified));
create policy restaurant_categories_owner_read on public.restaurant_menu_categories for select to authenticated
  using (exists(select 1 from public.vendors v where v.id=vendor_id and v.owner_id=(select auth.uid())));
create policy restaurant_items_public_read on public.restaurant_menu_items for select to anon, authenticated
  using (is_available and exists(select 1 from public.vendors v where v.id=vendor_id and v.type='restaurant' and v.is_active and v.is_verified));
create policy restaurant_items_owner_read on public.restaurant_menu_items for select to authenticated
  using (exists(select 1 from public.vendors v where v.id=vendor_id and v.owner_id=(select auth.uid())));
create policy restaurant_orders_customer_read on public.restaurant_orders for select to authenticated
  using (customer_id=(select auth.uid()));
create policy restaurant_orders_vendor_read on public.restaurant_orders for select to authenticated
  using (exists(select 1 from public.vendors v where v.id=vendor_id and v.owner_id=(select auth.uid())));
create policy restaurant_order_items_read on public.restaurant_order_items for select to authenticated
  using (exists(select 1 from public.restaurant_orders o join public.vendors v on v.id=o.vendor_id
    where o.id=order_id and (o.customer_id=(select auth.uid()) or v.owner_id=(select auth.uid()))));
create policy restaurant_order_payments_read on public.restaurant_order_payments for select to authenticated
  using (exists(select 1 from public.restaurant_orders o join public.vendors v on v.id=o.vendor_id
    where o.id=order_id and (o.customer_id=(select auth.uid()) or v.owner_id=(select auth.uid()))));
create policy restaurant_order_events_read on public.restaurant_order_events for select to authenticated
  using (exists(select 1 from public.restaurant_orders o join public.vendors v on v.id=o.vendor_id
    where o.id=order_id and (o.customer_id=(select auth.uid()) or v.owner_id=(select auth.uid()))));
grant select on public.restaurant_menu_categories, public.restaurant_menu_items to anon, authenticated;
grant select on public.restaurant_orders, public.restaurant_order_items, public.restaurant_order_payments,
  public.restaurant_order_events to authenticated;
