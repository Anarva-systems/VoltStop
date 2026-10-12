# Database

The initial schema is `supabase/migrations/202610020001_initial_schema.sql`.
It creates profiles, vendors, vendor services, charging slots, bookings,
payments, booking events, and notifications, with UUID keys, constraints,
foreign keys, update triggers, and supporting indexes. Vendor coordinates use
`extensions.geography(Point,4326)` and a GiST index; latitude/longitude are
kept synchronized. The `nearby_vendors(latitude, longitude, radius_km)` RPC
returns active verified vendors in distance order with active services and
available future slots. It is `SECURITY INVOKER`, so RLS applies to the
calling user.

`supabase/seed/202610020001_demo_corridor.sql` is development-only fictional
data. `supabase/verify.sql` checks PostGIS, schema, RLS activation, spatial
index, RPC output, and foreign keys after a reset. Run:

```sh
supabase start
supabase db reset
psql "postgresql://postgres:postgres@localhost:54322/postgres" -v ON_ERROR_STOP=1 -f supabase/verify.sql
```

Drivers can read/update only their own profile, see active verified vendors,
available slots, and their own bookings. Vendor access is scoped to
`vendors.owner_id = auth.uid()`; owners cannot change ownership, active, or
verification flags. Bookings and payment mutations are admin/backend-only;
users and vendors have read policies. Admin policies use the protected
`app_metadata.role = 'admin'` JWT claim, which must only be assigned by a
trusted auth-admin flow. Do not ship service-role keys to clients; trusted
backend operations may bypass RLS and must perform authorization themselves.

Capacity must be checked transactionally while locking the relevant slot row;
Redis locks are not a substitute for PostgreSQL transaction checks. Pending
booking expiry and slot-status updates must be maintained by the trusted API.
