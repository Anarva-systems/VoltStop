# VoltStop product audit — driver trips

## Existing architecture

- The mobile product has an authenticated driver shell with Home, Explore, Trips, and Profile navigation.
- The driver data model already supports user-owned EVs and saved route estimates. The route planner covers named pilot stops along NH-16 from Srikakulam to Vijayawada.
- The Trips area previously showed charger bookings and hotel stays. It had no durable driver trip record, schedule, status lifecycle, or discoverable trip listing.
- The vendor website is a separate vendor/admin surface. Driver trip controls have been added only to the mobile driver app.

## Implemented in this change

- Drivers can create, list, inspect, edit eligible scheduled trips, start, complete, or cancel their own trips.
- Trip dates are submitted/stored as timezone-aware UTC timestamps and rendered in the device timezone.
- A driver may opt into browse-only trip discovery, filter by NH-16 stop and local departure date, and disclose the listed vehicle, departure, and driver-provided seat count. Private notes, driver identity, and vehicle IDs are omitted from discovery results.
- Existing route estimates and VoltStop pitstop suggestions may be attached when the route service responds. A route-provider failure does not prevent a trip from being saved. Suggestions do not establish live charger status, pricing, compatibility, or reservations.
- Passenger bookings, seat allocation, fares, contact exchange, payments, and safety guarantees are not implemented.

## Authorization and product boundaries

Every trip read and mutation is scoped to the authenticated user's ID. Creation and editing verify that the selected saved vehicle belongs to that same user; client-supplied identity fields are rejected. The current product has no separate driver-role claim/table, so this is an authenticated mobile driver workflow backed by ownership checks, not a verified driver credential or vehicle-registration check. Do not describe it as such.

The vendor website has not gained trip-management controls. The mobile app's Trips page retains its existing charger/hotel reservation view alongside My drives and Discover.

## Production readiness still required

- Apply the additive migration to the intended database after confirming backup and migration order; no production database was changed here.
- Deploy the backend before shipping a client that calls the new endpoints.
- Verify the correct database is used by the API, auth/JWT behavior, migration/RLS permissions, and route provider in a staging environment.
- If public driver credentials, passenger coordination, or reservation guarantees are needed, define those policies and role onboarding separately before adding them.
