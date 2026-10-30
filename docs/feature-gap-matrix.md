# Feature gap matrix — driver trips

| Capability | Prior state | Current implementation | Remaining gap / verification |
| --- | --- | --- | --- |
| Driver trip creation | No trip CRUD | Authenticated API + mobile form; corridor stop, departure, optional arrival, saved EV, seats, notes, discovery opt-in | Apply migration and verify in staging |
| Driver trip ownership | No trip records | Reads and writes scoped to token subject; selected vehicle must be owned by that subject | No distinct driver-role or vehicle credential validation exists |
| Trip edits and cancellation | Not available | Only scheduled future trips can be edited; scheduled trips can be cancelled | No external arrangements or passenger booking are changed |
| Lifecycle status | No trip lifecycle | Scheduled, In Progress, Completed, Cancelled; explicit driver actions; no automatic transitions | Confirm operational policy for missed/late trips |
| Upcoming and past list | Trips showed reservations | Separate driver list filters plus existing reservations tab | No calendar sync; push transport exists server-side but no build obtains a device token |
| Trip discovery | Not available | Opt-in, authenticated, browse-only discovery by corridor stops and departure date | No seat requests/reservations, direct contact, passenger matching, fare, or payment |
| Route/charging suggestions | Existing route estimate and vendor pitstop listing | Optional estimate may be attached to a trip; provider outages do not block scheduling | No traffic-aware optimization, live CPO availability, charger pricing guarantees, or charger reservation |
| Vendor portal | Vendor/admin operations only | No driver trip controls added to vendor website | Keep role-specific controls separated |
| Data schema | No `driver_trips` table | Additive Supabase migration with constraints, indexes, idempotency, and owner-read RLS | Migrations have not been applied to any shared/production database |
| Automated verification | No trip tests | Backend: 145 passed, 3 skipped; Flutter: 45 passed; Dart analysis clean; debug APK built | Migration contract tests are static; no real database or deployed API verification |
| Mobile API connectivity | No live backend deployment | Debug APK built with Flutter's default Android-emulator API address | Physical phones need a reachable LAN/HTTPS API; no listener was found on local ports 8000 or 8001 |

## Enterprise product-readiness matrix — 19 October 2026

| Capability | VoltStop today | Priority and acceptance condition |
| --- | --- | --- |
| Corridor route planning | NH-16 pilot towns, EV charge estimate, route stops, and departure-time selection exist in the mobile app | **P1:** Confirm intermediate-town origin/destination behavior, vehicle-aware estimates, and route smoke tests against staging |
| Charger status and tariffs | Partner charging listings exist; live connector feed is not verified | **P0:** Integrate the provider API, expose source and freshness, and render stale/missing status as unknown |
| Nearby charger alerts | Foreground Explore alerts; no verified live CPO status or background push guarantee | **P1:** Trigger against provider status and implement consented push only after the provider and push path are monitored |
| Charging session lifecycle | No verified CPO start/stop/session telemetry integration | **P1:** Provider-backed start, session progress, stop, final energy/cost, and failure recovery |
| Payment integrity | Payment configuration is present; latest audit reports webhook setup incomplete | **P1:** Test order-to-webhook reconciliation, idempotent refund/capture handling, and customer receipt before live charging payments |
| Partner payouts | No transfer provider or payout ledger | **P1:** Keep payouts disabled; implement reconciled ledger, transfer status, reversals, and auditability before enabling |
| Partner portal | Profile, services, availability, bookings, support, and revenue surfaces exist | **P1:** Staging-verify vendor creation/listing, role isolation, profile persistence, responsive navigation, and booking lifecycle |
| Admin operations | Role-gated operations and audit workflows exist | **P1:** Verify real role grants, migrations, operational error/freshness dashboards, and sensitive-action audit records |
| Food and lodging around charge stops | Partner listings and hotel/restaurant flows exist in the product | **P2:** Verify actual hours, dates, inventory, confirmed reservation/refund state, and support handoff; do not imply charger/room availability from a listing |
| High-traffic readiness | No completed load/concurrency evidence in the 19 October audit | **P2:** Define a target workload, test API and database pool behavior, booking/payment concurrency, and provider rate-limit/backoff behavior |
| Release and observability | Web build passed in the prior audit; mobile/full backend suites and signed release were not verified there | **P2:** Complete platform checks, install/upgrade/deep-link/network tests, crash/error telemetry, and signed release gates |

## Closing matrix — 30 October 2026

| Capability | Prior state | Current implementation | Remaining gap / verification |
| --- | --- | --- | --- |
| Charger capability specs | `vendor_services` declared no plug or power | Migration `202610290001` adds `supported_connectors text[]` (CHECK-limited to CCS2, Type 2, CHAdeMO, Bharat AC, Bharat DC, Tesla) and `max_power_kw numeric(6,2)`; the vendor portal and both admin service tables render the pair and mark an incomplete declaration | Real vendors have not declared specs yet. An empty array or null kW is shown as "not declared", never inferred |
| Vehicle-aware corridor search | `route_pitstops(jsonb, double precision)` returned every charge stop | `route_pitstops(jsonb, double precision, text[])` filters charge units by the driver's connector list; `driver_vehicles.max_charging_kw` caps modelled charge power | Filter behavior is proven with test doubles only; no provider feed confirms a plug physically exists at the site |
| EV range physics | Consumption was distance ÷ nominal efficiency | `app/routes/energy.py` applies the configured derate, safety buffer, optimal charging window, per-stop arrival SoC, and charge minutes capped by `min(vehicle kW, station kW)`; Flutter mirrors the same thresholds | `EV_EFFICIENCY_DERATE` and the SoC windows are uncalibrated against real drives |
| Duplicate slot reservations | Overlap prevented only by the advisory lock plus `FOR UPDATE` | Migration `202610290002` adds an exclusion constraint on overlapping `charging_slots` windows. The `pg_advisory_xact_lock` + `FOR UPDATE` + Redis `SET NX EX` flow is unchanged | Constraint behavior under real concurrency needs the Postgres-backed run, not the mocked suite |
| Partner payouts | "No transfer provider or payout ledger" | Migration `202610290003` adds `vendor_payout_transfers` (`source_kind` limited to charging booking, hotel reservation, restaurant order) plus masked KYC columns on `vendor_onboarding`. `plan_payment_payout` splits at order creation and `record_payment_payout` writes a `planned` row; only signature-verified webhook events advance a row to processed/settled/failed/reversed. Admin `POST /admin/vendors/{id}/payout-routing` requires `payouts:manage`; `POST /admin/vendors/{id}/kyc` requires `vendor_onboarding:manage`. The 300 bps platform retention floor and the 5000 bps ceiling are validated server-side and in the portal | Live money movement is deliberately off: `VENDOR_SETTLEMENT_ENABLED` defaults to `false`, so splits stay `planned` and nothing is sent. Enabling it is a product decision requiring provider onboarding, a Razorpay Route-enabled account, and a test-mode reversal rehearsal |
| Notifications and push | In-app rows only, no device transport | Migration `202610290004` adds `user_push_tokens` and a `push_deliveries` outbox filled by an INSERT trigger on `notifications`, and adds `notifications`, `hotel_reservations`, `restaurant_orders` to the `supabase_realtime` publication. `app/notifications/push.py` sends FCM HTTP v1 with a service-account JWT, claims rows with `FOR UPDATE SKIP LOCKED`, and allows 6 attempts at 30 s backoff | No mobile build obtains a device token: `firebase_messaging` and the `google-services.json` / `GoogleService-Info.plist` files are intentionally absent, so nothing has been delivered to a real device and the FCM project is unconfigured |
| Mobile realtime and push client | Feeds refreshed on a timer only | `DriverRepository.watchNotifications()` streams `public.notifications` scoped to the token subject, beside the existing booking and pitstop watchers; `registerPushToken` / `unregisterPushToken` cover `PUT` and `DELETE /notifications/push-token` | The Dart suite has not been executed here — no Flutter toolchain in this workspace. `flutter analyze` and `flutter test` are still owed on the host |

## Blocking inputs

- Provider API documentation and a sanitized station/connector/status response are required before implementing the real charger feed.
- Staging credentials and a verified migration/backup state are required to prove production-style role, booking, and payment journeys. Do not put credentials in this matrix or Git.
- A Razorpay Route-enabled parent account, vendor linked-account IDs, and an explicit product decision to set `VENDOR_SETTLEMENT_ENABLED=true` are required before any transfer is sent. Keep the account ID and webhook secret out of this file and out of clients.
- An FCM project with a service-account JSON supplied through the API environment (never committed) and a mobile build that obtains a device token are required before push can be described as delivered rather than queued.
- Vendor-declared connector and power data for NH-16 partners is required before connector-filtered route results can be shown as complete.
