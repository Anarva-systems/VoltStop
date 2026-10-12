-- Internal administrator control plane. These tables are accessed only by the
-- trusted API database role; authenticated browser clients receive no grants.
create table public.admin_roles (
  name text primary key,
  description text not null
);

create table public.admin_permissions (
  permission_key text primary key,
  description text not null
);

create table public.admin_role_permissions (
  role_name text not null references public.admin_roles(name) on delete cascade,
  permission_key text not null references public.admin_permissions(permission_key) on delete cascade,
  primary key (role_name, permission_key)
);

create table public.admin_users (
  user_id uuid primary key references auth.users(id) on delete restrict,
  role_name text not null references public.admin_roles(name),
  is_active boolean not null default true,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index admin_users_role_active_idx on public.admin_users(role_name, is_active);

insert into public.admin_roles(name, description) values
  ('SUPER_ADMIN', 'Full platform access and administrator management'),
  ('OPERATIONS_ADMIN', 'Vendor, booking, availability, and live operations'),
  ('FINANCE_ADMIN', 'Transactions, payouts, and refunds'),
  ('SUPPORT_ADMIN', 'Customer support, bookings, and disputes'),
  ('VENDOR_MANAGER', 'Vendor onboarding, profiles, and verification')
on conflict (name) do nothing;

insert into public.admin_permissions(permission_key, description) values
  ('dashboard:read', 'View platform overview'),
  ('analytics:read', 'View platform analytics'),
  ('vendors:read', 'View vendor profiles'),
  ('vendors:manage', 'Approve, suspend, and reactivate vendors'),
  ('vendor_financials:read', 'View vendor level financial summaries'),
  ('vendor_onboarding:manage', 'Review vendor applications'),
  ('bookings:read', 'Search and inspect bookings'),
  ('operations:read', 'View corridor operations'),
  ('transactions:read', 'View payment transactions'),
  ('payouts:read', 'View payout calculations'),
  ('refunds:read', 'View refund records'),
  ('refunds:create', 'Issue verified payment refunds'),
  ('refunds:approve', 'Approve and submit a requested refund'),
  ('disputes:read', 'View disputes'),
  ('disputes:manage', 'Investigate and resolve disputes'),
  ('audit:read', 'Inspect immutable audit history'),
  ('admin_users:manage', 'Assign administrator roles and access'),
  ('roles:read', 'View administrator role permissions')
on conflict (permission_key) do nothing;

insert into public.admin_role_permissions(role_name, permission_key)
select 'SUPER_ADMIN', permission_key from public.admin_permissions
on conflict do nothing;

insert into public.admin_role_permissions(role_name, permission_key) values
  ('OPERATIONS_ADMIN', 'dashboard:read'),
  ('OPERATIONS_ADMIN', 'vendors:read'),
  ('OPERATIONS_ADMIN', 'vendors:manage'),
  ('OPERATIONS_ADMIN', 'vendor_onboarding:manage'),
  ('OPERATIONS_ADMIN', 'bookings:read'),
  ('OPERATIONS_ADMIN', 'operations:read'),
  ('FINANCE_ADMIN', 'dashboard:read'),
  ('FINANCE_ADMIN', 'transactions:read'),
  ('FINANCE_ADMIN', 'vendor_financials:read'),
  ('FINANCE_ADMIN', 'payouts:read'),
  ('FINANCE_ADMIN', 'refunds:read'),
  ('FINANCE_ADMIN', 'refunds:create'),
  ('FINANCE_ADMIN', 'refunds:approve'),
  ('SUPPORT_ADMIN', 'dashboard:read'),
  ('SUPPORT_ADMIN', 'bookings:read'),
  ('SUPPORT_ADMIN', 'disputes:read'),
  ('SUPPORT_ADMIN', 'disputes:manage'),
  ('VENDOR_MANAGER', 'dashboard:read'),
  ('VENDOR_MANAGER', 'vendors:read'),
  ('VENDOR_MANAGER', 'vendors:manage'),
  ('VENDOR_MANAGER', 'vendor_onboarding:manage')
on conflict do nothing;

create table public.vendor_onboarding (
  vendor_id uuid primary key references public.vendors(id) on delete restrict,
  status text not null default 'pending'
    check (status in ('pending','under_review','changes_requested','approved','rejected','suspended')),
  current_stage text not null default 'application'
    check (current_stage in ('application','business_details','documents','location','banking','verification','approval')),
  completed_stages jsonb not null default '["application","business_details","location"]'::jsonb
    check (jsonb_typeof(completed_stages) = 'array'),
  document_references jsonb not null default '[]'::jsonb
    check (jsonb_typeof(document_references) = 'array'),
  decision_reason text,
  reviewed_by uuid references auth.users(id) on delete set null,
  submitted_at timestamptz not null default now(),
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index vendor_onboarding_status_created_idx on public.vendor_onboarding(status, submitted_at desc);
insert into public.vendor_onboarding(vendor_id, status, current_stage)
select id, case when is_verified then 'approved' else 'pending' end,
       case when is_verified then 'approval' else 'application' end
from public.vendors on conflict (vendor_id) do nothing;

create or replace function public.initialize_vendor_onboarding()
returns trigger language plpgsql set search_path = '' as $$
begin
  insert into public.vendor_onboarding(vendor_id,status,current_stage)
  values(new.id,'pending','application')
  on conflict(vendor_id) do nothing;
  return new;
end;
$$;
create trigger vendors_initialize_onboarding after insert on public.vendors
  for each row execute function public.initialize_vendor_onboarding();

create table public.refunds (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid not null references public.bookings(id) on delete restrict,
  payment_id uuid not null references public.payments(id) on delete restrict,
  requested_by uuid not null references auth.users(id) on delete restrict,
  approved_by uuid references auth.users(id) on delete restrict,
  approved_at timestamptz,
  amount_inr numeric(12,2) not null check (amount_inr > 0),
  currency char(3) not null default 'INR' check (currency = 'INR'),
  reason text not null check (length(trim(reason)) > 0),
  status text not null default 'requested'
    check (status in ('requested','approved','processing','completed','failed','rejected')),
  idempotency_key text not null unique,
  razorpay_refund_id text unique,
  provider_status text,
  provider_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index refunds_booking_status_idx on public.refunds(booking_id, status, created_at desc);
create index refunds_created_idx on public.refunds(created_at desc);

create table public.disputes (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid not null references public.bookings(id) on delete restrict,
  reason text not null check (length(trim(reason)) > 0),
  description text not null check (length(trim(description)) > 0),
  status text not null default 'open'
    check (status in ('open','investigating','awaiting_customer','awaiting_vendor','resolved','closed')),
  evidence jsonb not null default '[]'::jsonb check (jsonb_typeof(evidence) = 'array'),
  resolution text,
  created_by uuid references auth.users(id) on delete set null,
  assigned_to uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index disputes_status_created_idx on public.disputes(status, created_at desc);
create index disputes_booking_idx on public.disputes(booking_id);

create table public.dispute_events (
  id uuid primary key default gen_random_uuid(),
  dispute_id uuid not null references public.disputes(id) on delete restrict,
  actor_user_id uuid references auth.users(id) on delete set null,
  event_type text not null,
  message text,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now()
);
create index dispute_events_dispute_created_idx on public.dispute_events(dispute_id, created_at);

create table public.admin_audit_logs (
  id uuid primary key default gen_random_uuid(),
  admin_user_id uuid not null references auth.users(id) on delete restrict,
  role_name text not null,
  action text not null,
  entity_type text not null,
  entity_id text,
  reason text,
  before_state jsonb,
  after_state jsonb,
  request_metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(request_metadata) = 'object'),
  created_at timestamptz not null default now()
);
create index admin_audit_created_idx on public.admin_audit_logs(created_at desc);
create index admin_audit_entity_idx on public.admin_audit_logs(entity_type, entity_id, created_at desc);

create or replace function public.prevent_admin_audit_mutation()
returns trigger language plpgsql set search_path = '' as $$
begin
  raise exception using errcode = '55000', message = 'Admin audit records are immutable';
end;
$$;
create trigger admin_audit_immutable
  before update or delete on public.admin_audit_logs
  for each row execute function public.prevent_admin_audit_mutation();

create trigger admin_users_set_updated_at before update on public.admin_users
  for each row execute function public.set_updated_at();
create trigger vendor_onboarding_set_updated_at before update on public.vendor_onboarding
  for each row execute function public.set_updated_at();
create trigger refunds_set_updated_at before update on public.refunds
  for each row execute function public.set_updated_at();
create trigger disputes_set_updated_at before update on public.disputes
  for each row execute function public.set_updated_at();

alter table public.admin_roles enable row level security;
alter table public.admin_permissions enable row level security;
alter table public.admin_role_permissions enable row level security;
alter table public.admin_users enable row level security;
alter table public.vendor_onboarding enable row level security;
alter table public.refunds enable row level security;
alter table public.disputes enable row level security;
alter table public.dispute_events enable row level security;
alter table public.admin_audit_logs enable row level security;

revoke all on public.admin_roles, public.admin_permissions, public.admin_role_permissions,
  public.admin_users, public.vendor_onboarding, public.refunds, public.disputes,
  public.dispute_events, public.admin_audit_logs from anon, authenticated;
