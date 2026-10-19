# Feature gap matrix — driver trips

| Capability | Prior state | Current implementation | Remaining gap / verification |
| --- | --- | --- | --- |
| Driver trip creation | No trip CRUD | Authenticated API + mobile form; corridor stop, departure, optional arrival, saved EV, seats, notes, discovery opt-in | Apply migration and verify in staging |
| Driver trip ownership | No trip records | Reads and writes scoped to token subject; selected vehicle must be owned by that subject | No distinct driver-role or vehicle credential validation exists |
| Trip edits and cancellation | Not available | Only scheduled future trips can be edited; scheduled trips can be cancelled | No external arrangements or passenger booking are changed |
| Lifecycle status | No trip lifecycle | Scheduled, In Progress, Completed, Cancelled; explicit driver actions; no automatic transitions | Confirm operational policy for missed/late trips |
| Upcoming and past list | Trips showed reservations | Separate driver list filters plus existing reservations tab | No push reminders or calendar sync |
| Trip discovery | Not available | Opt-in, authenticated, browse-only discovery by corridor stops and departure date | No seat requests/reservations, direct contact, passenger matching, fare, or payment |
| Route/charging suggestions | Existing route estimate and vendor pitstop listing | Optional estimate may be attached to a trip; provider outages do not block scheduling | No traffic-aware optimization, live CPO availability, charger pricing guarantees, or charger reservation |
| Vendor portal | Vendor/admin operations only | No driver trip controls added to vendor website | Keep role-specific controls separated |
| Data schema | No `driver_trips` table | Additive Supabase and Neon migrations with constraints, indexes, idempotency, and Supabase owner-read RLS | Migrations have not been applied to any shared/production database |
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

## Blocking inputs

- Provider API documentation and a sanitized station/connector/status response are required before implementing the real charger feed.
- Staging credentials and a verified migration/backup state are required to prove production-style role, booking, and payment journeys. Do not put credentials in this matrix or Git.
