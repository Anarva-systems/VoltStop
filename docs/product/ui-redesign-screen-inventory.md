# VoltStop UI/UX Redesign — Screen Inventory (PART 1)

Date: 2026-10-23 · Scope: `apps/mobile` (Flutter) + `apps/vendor-web` (Next.js 15) · Status: inspection complete, redesign in progress

## Reference video limitation (documented)

The two LinkedIn reference videos (`lnkd.in/p/dv4qSzQC`, `lnkd.in/p/dDrXeAKk`) could not be visually inspected from this environment. Per the brief, no details are invented from unseen video frames. The established design direction is used instead: premium EV corridor product — cream canvas `#F4F3EC`, forest `#1A4035` primary, lime `#B7DC68` accent, serif display headlines, generous whitespace, rounded surfaces, live-but-honest status messaging.

## Brand snapshot (inspected before selecting colors)

Existing VoltStop identity is **forest + lime on cream**, already consistent across the mobile theme (`apps/mobile/lib/core/theme/app_theme.dart`), the web home page (`app/home.css`), and the vendor portal light theme (`app/portal-refresh.css`). The redesign does **not** replace this identity; it extends and unifies it (see design system, PART 2).

---

## A. Flutter mobile — `apps/mobile`

Routes are imperative (`Navigator.push`); the shell is an `IndexedStack` + `NavigationBar` (Home / Explore / Trips / Profile). All screens below preserve their existing routes, APIs and workflows.

### A1. Onboarding — `OnboardingScreen` (`auth_screens.dart:13`)
- Role: signed-out driver. Functionality: marketing landing → "Continue with phone" → `PhoneAuthScreen`.
- Already premium: serif display headline, pilot-corridor card, `VoltButton`. **Problems:** none significant.
- Recommended: keep; minor copy polish only.

### A2. Phone sign-in — `PhoneAuthScreen` (`auth_screens.dart:253`)
- Role: signed-out driver. Functionality: +91 phone normalization (6–9 start, 10 digits), `sendOtp`, API readiness pre-check, Supabase-not-configured warning card.
- Already premium: card + label + validation copy. **Problems:** error text is plain red text (fine), no phone icon in field.
- Recommended: keep; add input prefix icon, unified inline error banner component (see design system).

### A3. OTP verification — `OtpScreen` (`auth_screens.dart:403`)
- Role: signed-out driver. Functionality: 6-digit verify, resend cooldown (60s), verify → profile load → `DriverShell` or `ProfileSetupScreen`; honest SMS-delivery disclaimers.
- Already premium. **Problems:** none significant.
- Recommended: keep; polish the "request status" card into a status-pill variant.

### A4. Profile setup — `ProfileSetupScreen` (`driver_screens.dart:25`)
- Role: new driver. Functionality: name/make/model/battery/efficiency validation, saves profile + creates or updates vehicle, routes to shell.
- Already premium (progress bar, centered icon, serif heading). **Problems:** plain `TextField` labels only; validation errors as plain text.
- Recommended: keep; error banner component; field-level helper consistency.

### A5. Driver shell — `DriverShell` (`driver_screens.dart:199`)
- Role: signed-in driver. Functionality: `IndexedStack` Home/Explore/Trips/Profile + Material `NavigationBar` (height 72, forest/lime themed).
- **Problems:** none structural. Recommended: keep.

### A6. Home / Dashboard — `HomeScreen` (`driver_screens.dart:539`)
- Role: driver. Functionality: journey welcome card (origin/destination, SoC ring — real profile data only), route planner card (NH-16 towns, departure picker, SoC slider persisted to profile/vehicle, live route estimate: distance/energy/arrival SoC), route stops preview (`PitstopCard` ×2), next reservation row, live refresh streams.
- Already premium: gradient welcome card, charge ring, `_DeparturePicker`. **Problems:**
  - Next-reservation row is a plain `ListTile` with raw `Status: confirmed` text — breaks the premium card language.
  - Route-estimate metric row uses `VoltColors.cyan` values (cyan alias = muted green, acceptable but inconsistent with forest).
- Recommended: replace the upcoming-booking tile with a compact status-pill card; align metric colors; keep all real data.

### A7. Station discovery — `DiscoveryScreen` (`driver_screens.dart:1479`)
- Role: driver. Functionality: OSM map + list toggle, search box, category filter chips, "Search this area"/"My location", nearby-alerts switch (geolocation, 5 km in-app alerts, honest "no live plug data" copy), corridor banner, `PitstopCard` list with images, prices, service chips.
- Already premium. **Problems:**
  - `PitstopCard` "Live connector status unavailable" chip is repeated word-for-word on every charging card — noisy.
  - Filter chips are default-styled `ChoiceChip`s; search field has a `tune` suffix icon that does nothing.
  - Cards stack full-width; no price/availability hierarchy.
- Recommended: restyle chips; remove inert tune icon (or wire filter sheet); tighten card meta row; keep map + alerts exactly as-is.

### A8. Station details — `PitstopDetailsScreen` (`driver_screens.dart:2198`)
- Role: driver. Functionality: hero image, name/verified, address, service list with prices, description, first 3 `_SlotTile` previews, CTA to `SlotSelectionScreen` (or hotel/restaurant flows), 30s live refresh.
- **Problems:** services are plain `ListTile`s; CTA buttons buried mid-scroll; slot tiles show "capacity" but no price emphasis; no sticky bottom action.
- Recommended: service rows with icons + price alignment; sticky bottom "Select slot" bar (only when slots exist); slot tile price pill.

### A9. Hotel booking — `HotelBookingScreen` (`driver_screens.dart:2420`)
- Role: driver. Functionality: check-in/out + times, guests/rooms steppers, room cards (real inventory + rates), price-review dialog, Razorpay checkout, verified-status polling. All real.
- **Problems:** guest/room stepper is cramped plain `IconButton`s; date buttons wrap awkwardly on narrow screens; status card is plain.
- Recommended: stepper into a dedicated counter row; status card with status-pill; keep every payment/verification behavior untouched.

### A10. Slot selection — `SlotSelectionScreen` (`driver_screens.dart:2878`)
- Role: driver. Functionality: server slot list, lock-on-select (`lockSlot`), 20s availability refresh, countdown handled on next screen.
- **Problems:** `_SlotTile` is a thin row — time, date, capacity, price all in one muted subtitle line.
- Recommended: two-line tile with time range as title, price pill + capacity chip as trailing meta; selected-state animation.

### A11. Booking review — `BookingReviewScreen` (`driver_screens.dart:3080`)
- Role: driver. Functionality: slot-hold countdown card, review rows (vendor/service/date/time/total), cancellation-policy copy, proceed to payment; expired state disables CTA.
- Already good. **Problems:** minor — plain `SelectableText` values; no service icon in header.
- Recommended: light polish only (icon header, price emphasis).

### A12. Secure payment — `PaymentScreen` (`driver_screens.dart:3258`)
- Role: driver. Functionality: creates booking (idempotent), opens Razorpay, verifies signature, polls server for **confirmed** status only — no fake success; failure/processing states with honest copy.
- **Problems:** ready state is a plain column (lock icon + price + copy); no slot/vendor summary shown while paying.
- Recommended: add compact booking summary card in ready state; keep all gateway logic identical.

### A13. Booking success — `BookingSuccessScreen` (`driver_screens.dart:3510`)
- Role: driver. Functionality: confirmed-only entry, check icon, booking id, CTA to Trips.
- **Problems:** very plain vs. the rest of the app.
- Recommended: premium confirmation card — animated check, booking reference pill, next-steps list, "View my trips" primary + "Back to home" secondary.

### A14. Trips hub — `DriverTripsScreen` (`upcoming_trips_screen.dart:23`)
- Role: driver. Functionality: 3 tabs (My drives / Discover / Reservations) where Reservations embeds `BookingsScreen`; driver-trip create/edit/start/cancel/complete; route estimates; discoverable-trip cards.
- **Problems:** two nested tab levels (DriverTripsScreen tabs → BookingsScreen's own 4 tabs); plain Material dropdowns/SegmentedButton; `_detailRow` fixed 132px label column overflow risk.
- Recommended: keep both tab levels (routes preserved) but visually differentiate (segmented control styling for driver trips, sub-tabs for reservations); fix detail-row layout to wrap on narrow screens.

### A15. My bookings — `BookingsScreen` (`driver_screens.dart:4016`)
- Role: driver. Functionality: 4 tabs (Upcoming/Completed/Cancelled/Hotel stays); live refresh streams; hotel reservation bottom-sheet details, cancellation-quote dialogs (refund/fee honesty), QR-free booking rows.
- **Problems:** booking rows are plain `ListTile`s (raw `• confirmed` subtitle, no status pill); empty states are bare centered text; hotel rows cram 3-line subtitles.
- Recommended: booking cards with status pill + service icon + date/time + price rows; icon-based empty states; hotel card redesign with refund notes as chips.

### A16. Booking details — `BookingDetailsScreen` (`driver_screens.dart:4328`)
- Role: driver. Functionality: live status refresh, review rows, QR (reference-only, honestly labeled), directions, cancellation quote flow, dispute entry.
- **Problems:** status is uppercase colored text (no pill); QR card plain; actions stack loosely.
- Recommended: status pill header; keep QR + disclaimer; action group into primary/secondary hierarchy.

### A17. Directions — `DestinationMapScreen` (`driver_screens.dart:4531`)
- Role: driver. Functionality: OSRM route from current location, polyline, fit-bounds, fallback map. **Problems:** none significant. Recommended: keep.

### A18. Route planner — `RoutePlannerScreen` (`driver_screens.dart:3652`)
- Role: driver. Functionality: full route plan (persist optional), map preview, recommended pitstops, arrival SoC, departure countdown. Mostly premium already. **Problems:** suggested-pitstop rows are plain `ListTile`s. Recommended: reuse `PitstopCard`-lite rows.

### A19. Profile — `ProfileScreen` (`driver_screens.dart:4738`)
- Role: driver. Functionality: gradient profile hero (avatar, phone, vehicle/battery/efficiency metrics), garage tiles (vehicles, vehicle profile, booking history), sign out, honest estimate footnote.
- Already premium. **Problems:** none significant. Recommended: keep.

### A20. Vehicles — `VehiclesScreen` (`vehicles_screen.dart:7`)
- Role: driver. Functionality: garage list, create/edit/delete, default selection, `_VehicleDialog` with connectors checklist.
- **Problems:** plain `Card` list rows with default `Chip`; hardcoded `fontSize: 20` header instead of serif display style; raw error strings; dialog unthemed.
- Recommended: themed vehicle cards (icon badge + default pill), VoltPageHeading header, error banner component, themed dialog fields.

### A21. Restaurant menu/orders — `RestaurantMenuScreen` (`restaurant_screens.dart:8`)
- Role: driver. Functionality: menu categories, option dialogs, cart, Razorpay pickup payment, idempotent order creation, 10×2s verified-status polling, orders tab.
- **Problems:** orders tab uses plain `Card` + `ExpansionTile` with raw status strings; empty states are bare text; raw error strings.
- Recommended: status-pill order cards; icon empty states; preserve all payment/verification logic.

### A22. Disputes — `DisputesScreen` / `DisputeDetailsScreen` / `CreateDisputeScreen` (`dispute_screens.dart`)
- Role: driver. Functionality: list, thread with 4000-char messages, create with idempotency keys.
- **Problems:** plainest screens in the app — default `Card`s, raw `Status:` text, bare empty states, `VoltColors.cyan` timeline icons off-palette.
- Recommended: themed dispute cards with status pills, timeline with forest/lime dots, icon empty states.

---

## B. Next.js web — `apps/vendor-web`

All routes preserved. Shells: vendor `PortalShell` (`components/portal.tsx`) with 14 nav items; admin `AdminShell` (`components/admin-portal.tsx`) with grouped nav (Overview / Operations / Finance / Risk & Support / System).

### B1. Marketing home — `/` (`app/page.tsx`)
- Role: public. Functionality: hero, corridor strip, journey steps, partner band, footer. Already light cream theme.
- **Problems:** duplicate `id="corridor"` (lines 68, 82); no per-route metadata anywhere.
- Recommended: fix duplicate id; add per-page `<title>` via metadata in root layout where feasible (title template).

### B2. Login — `/login`, `/login/reset` (`app/login/page.tsx`)
- Role: vendor/admin. Functionality: Supabase password sign-in, role resolution → portal or admin, password reset, resend confirmation, show/hide password, honest unconfigured-Supabase warning.
- Well-formed. **Problems:** verbose copy; minor. Recommended: light copy trim only.

### B3. Vendor dashboard — `/vendor/dashboard`
- Role: vendor. Functionality: metrics, today's schedule, recent activity, incoming requests (accept without confirmation), availability summary.
- **Problems:** accept has no confirmation dialog; availability bar always renders 100% width regardless of real capacity (misleading); missing-profile handling string-matches error text; inline styles (lines 68–75).
- Recommended: confirmation dialog on accept; compute real availability % (booked/total slots) or hide bar when unknown; EmptyState CTA for missing profile; remove inline styles.

### B4. Vendor bookings — `/vendor/bookings` (+ `[bookingId]`)
- Role: vendor. Functionality: search/status filter, accept action (no confirm), view links, responsive table.
- **Problems:** no pagination (client fetch-all); accept without confirmation.
- Recommended: add confirmation on accept; keep filter behavior; table polish via design tokens.

### B5. Vendor services — `/vendor/services`
- Role: vendor. Functionality: service CRUD (add/edit/pause/price), modal form with validation, weekday chips. On-theme.
- **Problems:** inline styles (lines 94, 101). Recommended: token cleanup only.

### B6. Vendor revenue — `/vendor/revenue`
- Role: vendor. Functionality: revenue hero, stats, honest "commission is an estimate" note. On-theme. **Problems:** inline `marginTop`. Recommended: cleanup only.

### B7. Vendor profile/settings/requests/disputes/support/notifications/availability/pricing/hotels/restaurants
- Role: vendor. All use shared PortalShell components (`PageHeader`, `Panel`, `data-table`, `StatePill`, modals). Consistent with the light theme.
- **Problems (cross-cutting):** `StatePill` unknown statuses fall back to generic gray (acceptable); vendor-side confirmations missing for accept-type actions; `useVendorQuery` re-renders every 10s.
- Recommended: token-level polish; confirmation dialog helper reused across accept/cancel actions.

### B8. Admin overview — `/admin`
- Role: admin. Functionality: 10 metrics, two bar-chart cards, legend, quick links. Uses `admin-card`/`admin-metric` from admin.css + light overrides.
- **Problems:** chart labels overflow-hidden/cramped; charts have no empty-state CTA; quick links reuse vendor `.button` classes (cross-system).
- Recommended: chart label rotation/truncation + empty state; dedicated admin button style.

### B9. Admin vendors + onboarding — `/admin/vendors`, `/admin/vendor-onboarding`, `/admin/vendors/[vendorId]`
- Role: admin. Functionality: search/status/type/location filters, approve/suspend/reject/reactivate with required-reason dialogs (good pattern), detail page.
- **Problems:** hardcoded dark-theme inline colors `#8194a8` in `components/admin-vendor-list.tsx:34-35` that survive the light theme; pager plain buttons.
- Recommended: replace inline colors with tokens; style pager; keep all action dialogs.

### B10. Admin bookings — `/admin/bookings`
- Role: admin. Functionality: 7 filters (search/status/payment/service/vendor/date range), paginated list, inspect modal with detail grid + timeline. Read-only by design.
- **Problems:** filters are placeholder-only inputs without labels (a11y); toolbar cramped; URL `?search` read but never synced back.
- Recommended: label each filter (visually-hidden or floating), wrap toolbar, keep read-only semantics.

### B11. Admin finance/support/system — transactions, payouts, refunds, hotel-refunds, complaints, support, admin-users, roles, audit-logs, analytics, live-operations, restaurant-orders, availability, customers, routes, services, pricing, notifications, settings
- Role: admin. All read via `adminApi` with `useAdminQuery`, `AdminTable`, filters, pagers, action dialogs where destructive.
- **Problems (cross-cutting):** plain pager buttons; `admin-action` dialogs only pattern with confirmation (good); hardcoded inline colors in a few components; filters without labels.
- Recommended: token + pager + label polish; preserve every admin workflow and permission gate (`AdminGuard`).

---

## C. Cross-application issues (priority order)

1. **Two competing light palettes on web** — `admin.css` light block (`#187b43`, `#f5f7f5`) vs `portal-refresh.css` (`#1b7650`, `#fffefa`) vs `globals.css` light override (`#16834a`). Single source of truth needed (PART 2).
2. **Status presentation inconsistent** — mobile shows raw status strings (bookings, hotel, orders, disputes); web has `StatePill`. Mobile needs a status-pill widget.
3. **Empty/error states inconsistent** — web has `EmptyState`/`ErrorState`; mobile uses bare centered text in 5+ screens.
4. **Confirmations missing on vendor accept actions** — vendor dashboard + bookings accept bookings without dialogs; admin has the pattern already.
5. **Hardcoded colors/font sizes** — inline `#8194a8` (admin-vendor-list), `fontSize: 20` headers (vehicles), `VoltColors.cyan` accents that clash with forest/lime (mobile timelines, metrics).
6. **Raw exception strings** shown to users in mobile vehicles/disputes/restaurant screens.
7. **Misleading UI** — vendor availability bar always 100%; must reflect real booked/total or hide.
8. **A11y** — admin filter inputs unlabeled; duplicate `id="corridor"`; modals lack Esc/focus-trap (documented, low-risk to add Esc handling).
