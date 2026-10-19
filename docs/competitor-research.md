# VoltStop competitor benchmark — 19 October 2026

## Scope and evidence

This is a desk review of public company pages and Google Play listings, not hands-on testing of competitor apps. Store listings and company pages describe vendor-reported capabilities and scale; they do not independently verify uptime, availability accuracy, or successful payment/charging flows. Re-check claims before using them in public marketing.

## Product categories

VoltStop currently combines a driver route/discovery app with a vendor portal and an internal operations console. The closest comparisons are not all identical businesses:

| Product | Publicly described strengths | What VoltStop should learn |
| --- | --- | --- |
| Statiq | Consumer app discovery, live charger status, route planning, in-app payment/session features, nearby amenities, and a separate charging-station management platform. | Connect the complete driver journey to a real data source; develop provider operations alongside the app. [Consumer app](https://www.statiq.in/ev-charging-app), [route planner](https://www.statiq.in/route-planner), [CSMS](https://csms.statiq.in/) |
| Bolt.Earth | App listing describes map discovery, connector and price details, QR-based session start, live session tracking, payments, history, route discovery, alerts, and host management. | Make map-to-session transitions simple and give partners a practical way to manage listings and availability. [Google Play listing](https://play.google.com/store/apps/details?id=com.revos.bolt.android) |
| ChargeZone | App listing describes station search, compatibility and availability, navigation, session management, payment, booking/history, and customer support. | Make compatibility, booking state, and failure recovery visible on each charging journey. [Google Play listing](https://play.google.com/store/apps/details?hl=en_GB&id=com.chargezone) |
| Tata Power EZ Charge | App listing describes station discovery, advance booking, Auto Charge, trip planning, and fleet solutions. Its partner listing describes operational monitoring and revenue reporting. | Keep customer charging and partner operations as connected but role-separated experiences. [Driver app](https://play.google.com/store/apps/details?hl=en-US&id=com.tatapower.evapp), [partner app](https://play.google.com/store/apps/details?hl=en_US&id=com.tatapower.ez_charge_partner) |
| MG eHUB | Play listing positions it as a multi-network app with discovery, trip planning, payments, and session tracking across partner networks. | Drivers may compare VoltStop with aggregators even if VoltStop begins with one corridor. [Google Play listing](https://play.google.com/store/apps/details?id=com.mgmotor.ehub) |

## VoltStop’s present position

- VoltStop has a Flutter driver app, a Next.js partner/admin surface, a FastAPI backend, and a defined NH-16 pilot corridor. It supports route estimates and discovery of VoltStop partner listings, food, and stays.
- Its route and battery figures are estimates. A charge-point operator feed has not been verified in the application, so connector-level availability and live charging prices must not be claimed.
- Payment collection configuration exists, but the latest application audit reports payment webhooks as unconfigured. Vendor transfers and a payout ledger are not implemented.
- The partner and admin surfaces have useful operational breadth, but role registration, vendor persistence, migration state, and end-to-end journeys still need staging verification.
- Prior mobile work explicitly labels station listings and foreground-only proximity alerts; it does not present them as live charger telemetry or background push notifications.

## Positioning recommendation

Position VoltStop as the **trusted NH-16 travel-stop companion**: a driver can plan between supported towns, discover verified corridor partners, and coordinate charging with food or lodging. Start with reliable depth on this corridor instead of claiming national coverage or parity with large charging networks.

Differentiation should come from:

1. Accurate, timestamped charger information from the provider feed.
2. Useful stops for the time spent charging: food, rest, and stays with real opening hours and confirmed booking details where supported.
3. Clear route choices for intermediate towns, departure time, vehicle, and battery state.
4. Reliable partner operations and support when a listing, charger, booking, or payment fails.

## Prioritized product gaps

### P0 — verified charging data

Implement a backend adapter for the provider API only after its non-secret documentation and a sanitized station/connector response are available. Normalize site, EVSE/connector, power, tariff, operational status, source, and `last_updated` fields. Treat missing or stale data as unknown; never silently convert it to “available.” Keep provider credentials server-side.

### P1 — driver journey

- Make the map and route planner the primary entry points: current location or any pilot town, destination, departure date/time, vehicle, and current state of charge.
- Show route stops with connector compatibility, power, provider-reported status and freshness, price source, opening hours, detour, and verified amenities.
- Where the provider supports session control, build scan/start, live progress, stop, receipt, and support flows. Keep each action hidden until it is backed by the provider and confirmed payment lifecycle.
- Ask for notification permission clearly; offer nearby alerts only at the background/foreground level actually implemented.

### P1 — payments and trust

Complete test-mode order creation, checkout verification, signed webhook processing, idempotent capture/refund reconciliation, receipts, and support paths before enabling live charging payments. Keep vendor payouts unavailable until transfers, a double-entry/reconciliation ledger, failure handling, and audit controls exist.

### P1 — partner operations

Give partners an onboarding checklist, profile completeness and verification state, service/room/menu management, opening hours, availability, booking inbox, support workflow, and accurate revenue status. Separate vendor, driver, and administrator capabilities in both navigation and API authorization.

### P2 — scale and operational readiness

Monitor API/database/provider freshness, payment/webhook errors, and notification delivery. Add migration/version evidence, backups and restore drills, rate limits, idempotency, concurrency checks, and load tests before making a large-user-capacity claim.

## Product design principles

- Show the user what is actionable now: **Live and updated at**, **Partner listing**, **Hours not confirmed**, or **Temporarily unavailable**.
- Put navigation, call, and support actions on station and business details; do not bury the next step in a map marker.
- Use the same identity, status, price, and booking language across mobile, partner portal, and admin console.
- Keep marketing visuals distinct from live operational maps. State the corridor and coverage boundaries plainly.
- Optimize for fast scanning, legible contrast, accessible touch targets, mobile keyboard behavior, and useful loading/empty/error states.

## External dependency to unblock implementation

The VoltStop owner has confirmed a provider API exists, but its documentation and data contract have not yet been supplied. Needed next: the documentation URL/name, authentication method (describe only—do not send credentials), station/connector status definitions, rate limits, and one sanitized response sample. Put actual credentials only in local/Vercel environment settings.
