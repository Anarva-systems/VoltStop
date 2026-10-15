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
