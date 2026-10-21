# VoltStop — UX Audit

**Date:** 2026-10-21
**Scope:** Flutter mobile app (`apps/mobile`), Next.js vendor portal + admin (`apps/vendor-web`). Static code audit + live staging render check; no in-person device testing. Companion evidence in `voltstop-current-state-audit.md`.

---

## 1. Design system state

### 1.1 What exists

**Mobile** (`apps/mobile/lib/core/theme/app_theme.dart`) — the strongest foundation:
- Centralized Material 3 theme: `ColorScheme.fromSeed` with forest `#1A4035`, lime `#B7DC68`, warm cream `#F4F3EC`
- Defined spacing scale, border radii, elevation usage
- Serif headline treatment via system `'serif'` family (no bundled font)
- Enforced minimum tap targets: buttons 48×54 / 48×50
- Shared widgets: `VoltLoading`, `VoltError` (with retry), consistent empty states
- Contrast: forest-on-cream ≈ 8:1; muted `#53685E` ≈ 5:1 — generally WCAG AA-safe

**Web** (`apps/vendor-web`) — functional but fragile:
- Custom in-house kit: `Panel`, `Button`, `StatePill`, `Skeleton`, `ErrorState`, `EmptyState`, `ToastViewport`, `Icon` (inline SVG map), `AdminTable`, `AdminCard`, `AdminActionDialog`
- CSS variables declared in `globals.css` (dark palette) then **overridden twice**: `portal-refresh.css` light theme, then a second admin light block in `admin.css`, plus `--home-*` palette for marketing. Three layered token sets — theming is fragile and hard to reason about.
- **Tailwind v4 is installed but unused** — zero utility classes in the codebase; all hand-written CSS
- No shared tokens between mobile and web (expected for now, but the premium upgrade should define one token language per platform, documented once)

### 1.2 What's missing (design-system level)

| Gap | Class | Impact |
|---|---|---|
| Single source of truth for color/spacing/typography tokens | 2 | Token drift risk; three web palettes |
| Reusable status badges (state pills exist; mobile lacks equivalent) | 2 | Status semantics re-implemented ad hoc |
| Dialog/modal consistency across mobile (bottom sheets vs dialogs mixed) | 2 | Inconsistent mental model |
| Icon system on web (inline SVG map works; no sizing/spacing standard) | 2 | Icon inconsistencies |
| Focus-visible states on all interactive elements (web) | 3 | Keyboard users lose focus indication on most buttons/table actions |
| Dark mode (mobile) | 4 | Absent |
| Text-scale-aware layouts (mobile) | 4 | Only Discovery header adapts; fixed sizes break at large font scales |
| Skip links / landmark structure (web) | 4 | Screen-reader navigation cost |

---

## 2. Loading, empty, error, retry states

**Overall: class 1-2 — this is the platform's UX strength.**

- **Mobile**: `VoltLoading`/`VoltError` with retry on every screen; `FutureBuilder` error branches on Home, Discovery, Pitstop details, Hotel, Restaurant, Bookings, Trips, Disputes, Vehicles, RoutePlanner; every list has a guided empty state; profile-recovery screen with categorized failure messages; silent keep-last-data on background refresh failure (deliberate, commented).
- **Web**: skeletons on every query, `ErrorState` with retry, `EmptyState` with guidance, mutation toasts, 10s auto-refresh when tab visible + online.
- **Notable mobile behaviors worth preserving in any redesign**:
  - `/ready` pre-flight before OTP request/verify — a dead backend never burns a user's SMS code
  - 20–30s periodic refresh with realtime where available (booking status, slots)
  - Honest copy for unverifiable states ("The stay is booked only after VoltStop confirms the verified payment", "Live connector status unavailable")

**Gaps**: no offline cache or retry-with-backoff (mobile); no optimistic updates (web — acceptable, but slow-feeling forms); no skeleton→error transition standards on web admin tables (they just blank).

---

## 3. Form validation & error handling

| Surface | Class | Notes |
|---|---|---|
| Mobile forms | 1 | Phone normalization (+91, 6–9 prefix), 6-digit OTP regex, 60s resend cooldown, battery/efficiency/SOC bounds, trip-form invariants (distinct stops, future departure, arrival > departure), hotel guest/room bounds, dispute min-lengths. Some numeric fields use inline `tryParse` rather than `Form` validators — coverage complete, consistency imperfect |
| Mobile API errors | 1 | Typed `ApiException` taxonomy (auth/authorization/not_found/validation/server/timeout/tls/dns/network/readiness/deployment_unavailable) with human messages |
| Web forms | 1 | Native HTML validation + client checks (lat/lng range, URL scheme, price ≥ 0, refund ≤ remaining) + server 422 field mapping; mutations disable buttons while busy |
| Web API errors | 1 | Unified `responseErrorMessage`; ≥500 responses surface `x-request-id`/`x-vercel-id` for support; error codes preserved |
| Backend validation errors | 1 | Pydantic `extra="forbid"`, consistent `{success, error:{code,message}}` envelope, 422 details |

**Gaps**: no inline field-level error messages on web forms (errors appear as toasts/banners, not under fields); mobile lacks retry-with-backoff on transient network errors; no error boundary/`error.tsx` on web (default Next 404 only).

---

## 4. Navigation & information architecture

- **Mobile**: 4-tab shell (Home, Discovery, Reservations/Trips, Profile). Deep but flat push navigation without named routes — deep-linking impossible, back-stack management manual. `DisputesScreen` is **dead code** (unreachable — no navigation references it).
- **Web vendor**: 15 pages under `/vendor/(protected)` with sidebar; booking-related pages split across Requests/Bookings/Detail — reasonable. Marketing → login → dashboard funnel clear.
- **Web admin**: 22 pages under `/admin/(secure)`; some duplication (`/admin/complaints` re-exports disputes page) and an informational-only `/admin/routes` page with no function — candidates for consolidation in the redesign.
- **Route protection (web)**: client-only guards; unauthenticated users can download page bundles. Functional but should be stated as a known constraint; server-side middleware/proxy protection is a hardening item, not UX.
- **Search**: web admin global search passes `?search=` to bookings; vendor bookings search is client-side; mobile discovery search is client-side. No unified search suggestions.

---

## 5. Accessibility findings

| Issue | Surface | Severity |
|---|---|---|
| No `:focus-visible` outline on most web buttons/table actions (only nav links, modal cards, password toggle) | Web | High |
| Admin table typography at 8–10px | Web admin | High (legibility) |
| No skip links / landmark structure | Web | Medium |
| 7–11px labels (charge ring, eyebrows, chips) | Mobile | Medium |
| No text-scale-aware layouts (one exception) | Mobile | Medium |
| Contrast generally safe (8:1 / 5:1) | Mobile | Good |
| `aria-label` on icon buttons, `aria-current`, `role=alert/status`, `aria-modal`, `aria-live` map picker present | Web | Good |
| Color not the only channel? Partially — status pills use text + color; mobile statuses mostly text | Both | Acceptable |
| No reduced-motion handling | Both | Low |

---

## 6. Honest-data practices (preserve these)

The product is unusually disciplined about not fabricating capability — a redesign must not regress this:

- Mobile: "Live connector status unavailable" on every charging card; "Slot listings do not confirm a charger is free right now"; "QR gate validation is not yet available"; schematic corridor map labelled as illustrative; "Distance unavailable"/"Price not listed" instead of invented values
- Web admin: `/payouts` states "does not send money"; `/live-operations` states "no GPS/telemetry"; `/admin/settings` reports settlement "not implemented"; marketing page artwork labelled "ILLUSTRATIVE ROUTE"
- Vendor dashboard disclaimer: "Rejections and refunds are not enabled by the current booking lifecycle"

No mock data, no fake metrics anywhere. **Class 1.**

---

## 7. Prioritized UX issues (implementation order in roadmap)

| # | Issue | Class | Effort |
|---|---|---|---|
| 1 | Web token consolidation (one palette, one token file, remove layered overrides) | 2 | S |
| 2 | Web focus-visible states + minimum admin table font sizes | 3 | S |
| 3 | Mobile dead-code removal (`DisputesScreen`) + stale golden artifacts | 3 | S |
| 4 | Web `error.tsx`/`loading.tsx`/`not-found.tsx` boundaries | 4 | S |
| 5 | Field-level validation errors on web forms | 2 | M |
| 6 | Mobile text-scale-aware layouts + dark mode | 4 | M |
| 7 | Screen redesigns (home/discovery → details → checkout → history → vendor → admin) per roadmap batches | 2 | L |
| 8 | Skip links + landmark structure on web | 4 | S |
| 9 | Search suggestions + server-side category filters | 2 | M |
| 10 | Offline cache / retry-with-backoff (mobile) | 4 | M |
