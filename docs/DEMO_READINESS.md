# VoltStop client demo readiness

This checklist describes the current persisted flows and the configuration needed to demonstrate them. Do not insert sample customer, vendor, booking, payment, or charger records directly into a live database.

## Start the local applications

1. Start PostgreSQL/Supabase and Redis using the configured services. Docker is not part of this procedure.
2. Apply the Supabase migrations in order. In particular, the hotel reservations migration and `202610110003_restaurant_orders.sql` must be applied before hotel reservations or restaurant menus are used. The Neon mirror for the restaurant schema is `apps/api/migrations/neon/003_restaurant_orders.sql`.
3. Start FastAPI from `apps/api` with the repository Python environment and `PYTHONPATH` set to `D:\voltstop\apps\api`, listening on port `8001`.
4. Start the vendor/admin Next.js website from `apps/vendor-web` on port `3002`. The API's `VENDOR_PORTAL_ORIGIN` must match that origin.
5. For the Android emulator, run Flutter with `--dart-define=API_BASE_URL=http://10.0.2.2:8001/api/v1`. For a physical device, use the development machine's reachable LAN address instead of `10.0.2.2`.

## Prepare authorized demo records

- Sign in with a designated restaurant vendor account, submit its business profile, and have an authorized administrator approve it.
- Use **Vendor → Restaurant menu** to add categories and items. The customer app reads these records through the API; the website does not supply a hardcoded sample menu.
- Use the hotel management screen to create room types and nightly inventory before demonstrating hotel reservations.
- A sample database seed was not run: the repository has no approved demo restaurant owner/vendor identity, and fabricating or inserting records into the configured database would create misleading business data. If a separate demo database and authorized demo vendor are provisioned, seed that environment only.

## Payments

The client supplied a Razorpay test key ID earlier, but the API also needs the matching `RAZORPAY_KEY_SECRET` and a `RAZORPAY_WEBHOOK_SECRET`. Keep both server-only. Configure Razorpay's webhook to reach `/api/v1/payments/razorpay/webhook` and subscribe to captured/failed payment events. A checkout remains unavailable when any required API credential is missing. Client SDK callbacks never mark an order or reservation paid; the database changes only after a signature-verified webhook. Do not reuse test credentials in production.

Restaurant pickup orders now have a persisted menu, server-priced cart, idempotent order creation, immutable item snapshots, webhook-authoritative payment, vendor fulfillment transitions, customer history, and an admin read-only monitor. Refunds and cancellation of paid food orders are not enabled: the current finance system cannot safely bind its existing refund workflow to restaurant order payments. The admin monitor flags late payment captures for refund review; it does not claim that a refund has been issued.

## Maps and EV operations

- Map/list discovery and coordinate confirmation remain available. Address autocomplete and reverse geocoding remain disabled because no new geocoding data transfer has been authorized.
- Existing charging slots are booking inventory. There is no charger-network/operator API, OCPP/device connection, connector inventory table, or telemetry feed in this repository. Therefore no physical charging session can be started or reported as live. A client demo should show discovery and the existing slot reservation only, and state this hardware integration limit clearly.
