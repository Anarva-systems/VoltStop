# VoltStop — Current State Audit

**Date:** 2026-10-21
**Scope:** complete repository at `D:\voltstop-1\production-work` (FastAPI backend, Next.js vendor web + admin, Flutter mobile, Supabase Postgres/Auth, Razorpay, Redis)
**Method:** full source read of every router, page, screen, migration and test file; backend and web test suites executed this session. Staging (Vercel + Supabase) was deployed and smoke tested end-to-end on 2026-10-20 (see `docs/phase-30-staging-project-bootstrap.md`). Production state is unknown — see §9.

**Classification key used throughout:**
1. Implemented and verified (tests and/or live staging evidence)
2. Implemented but incomplete
3. Present but broken
4. Missing
5. Blocked by an unavailable integration or credential

---

## 1. Executive summary

VoltStop is a functional, unusually well-engineered booking platform for an NH-16 EV travel corridor. The backend is the strongest layer: 100+ endpoints with role/ownership checks, atomic capacity allocation, webhook-authoritative payment capture, cancellation policy snapshots, and a 157-test suite (153 pass, 3 skipped integration probes, 1 failing — root cause identified). The database has 37 tables, all RLS-enabled, with a deliberate index strategy. The mobile app (Android-only) and the web portal/admin are fully wired to real APIs with no mock data anywhere. Staging was genuinely verified end-to-end: vendor onboarding → approval → slot → booking → Razorpay test payment → capture.

The platform is not "premium-complete" yet. The recurring themes are: **(a)** reliability edge cases in the money path (pending-booking expiry, booking idempotency, one-active-refund guarantee), **(b)** one real schema drift bug (hotel operating-hours columns missing from migrations), **(c)** missing growth features (reviews, favourites, push notifications, offers), **(d)** missing operations infrastructure (no CI, no rate limiting, no security headers, no verified webhook delivery, no production deployment evidence), and **(e)** UX polish gaps (no shared design system, weak focus states, dead screens).

**Headline numbers**

| Layer | Size | Test status (this session) |
|---|---|---|
| Backend API | ~15 routers, 100+ endpoints | 153 passed / 1 failed / 3 skipped (pytest) |
| Database | 15 migrations, 37 tables, 20 functions, 24 triggers | Applied on staging; production ledger unknown |
| Mobile | 20+ screens, ~49 Dart tests | Not runnable (Flutter CLI absent); passed 2026-10-11 per docs |
| Web (vendor + admin) | 46 routes | 13/13 node:test pass; no jest/playwright |
| CI/CD | none | 4 |

---

## 2. Platform components and deployment state

| Component | Location | State |
|---|---|---|
| API | `apps/api` (FastAPI, `index.py` → `app.main:app`), mounted at `/api/v1` | Deployed on Vercel: staging `voltstop-staging-api.vercel.app` (verified), production `volt-stop` project (state unknown) |
| Vendor web + admin | `apps/vendor-web` (Next.js 15 App Router) | Staging `voltstop-staging-web.vercel.app` renders and is wired to staging API (verified); production unknown |
| Mobile | `apps/mobile` (Flutter, Android-only, v0.1.2+8, no `ios/`) | No store/CI build pipeline evidence; debug/release APKs built locally per docs |
| Database | `supabase/migrations` (15 files), Supabase Postgres + Auth | Staging project "VoltStop Staging" (ap-south-1) has all 15 migrations applied (verified via `migration list`); production ledger unverified |
| Cache/locks | Redis (Upstash) | Staging verified; shares instance DB 0 with production via `REDIS_KEY_PREFIX=staging:` (uncommitted code change — see §5.7) |
| Payments | Razorpay | Staging test-mode capture verified end-to-end; webhook delivery NOT verified anywhere (secret intentionally unset) |

---

## 3. Backend audit (`apps/api`)

### 3.1 Endpoint inventory (all under `/api/v1`)

Auth: **P** public, **B** bearer (CurrentUser), **A** admin permission, **V** vendor-owner scoped.

| Domain | Endpoints | Auth |
|---|---|---|
| Health | `GET /`, `/health`, `/ready` (DB/Auth/Redis probes + capability flags) | P |
| Auth | `POST /auth/verify`, `GET /auth/me` | P / B |
| Profile | `GET/PATCH /profile` (allow-listed fields) | B |
| Vehicles | `GET/POST /vehicles`, `GET/PATCH/DELETE /vehicles/{id}`, `POST /vehicles/{id}/default` (POST requires `Idempotency-Key`) | B, owner-scoped |
| Vendors (public) | `GET /vendors/nearby`, `/vendors/{id}`, `/vendors/{id}/slots`, `GET /slots/{slot_id}` | P |
| Routes/driver | `POST /routes/plan` (OSRM), `POST/GET /routes/trips`, `GET /routes/trips/discover`, `GET/PUT /routes/trips/{id}`, lifecycle `start|complete|cancel` (create requires `Idempotency-Key`) | B, owner-scoped |
| Bookings | `POST /bookings/lock`, `POST /bookings`, `GET /bookings`, `GET /bookings/{id}`, `GET /bookings/{id}/cancellation-quote`, `POST /bookings/{id}/cancel` | B, owner-scoped |
| Payments | `POST /payments/razorpay/verify` (B), `POST /payments/razorpay/webhook` (HMAC) | B / P-HMAC |
| Vendor portal | `/vendor/profile` CRUD, `/dashboard`, `/bookings` + `accept|complete`, `/disputes` + messages, `/availability` CRUD, `/services` CRUD, `/revenue` | B→vendor owner |
| Admin | `/admin/me`, `/dashboard`, `/analytics`, `/vendors` + actions + financials, `/vendor-onboarding` + action, `/bookings`, `/live-operations`, `/transactions`, `/payouts`, `/refunds` (eligibility/create/approve/reject), `/hotel-refunds`, `/disputes` + actions + refund-request, `/audit-logs`, `/financial-diagnostics`, `/roles`, `/admin-users`, `/customers`, `/availability`, `/services` (moderate), `/pricing`, `/settings`, `/notifications` | A — permission-gated (see §3.2) |
| Hotels | customer: rooms/quotes/reservations/cancel; vendor: room CRUD, dated inventory PUT, reservations | B, owner-scoped |
| Restaurants | customer: menu/orders; vendor: categories/items/orders/status/financials; admin: order monitor | B, owner-scoped |
| Support | customer/vendor `GET/POST /support`, messages (`Idempotency-Key`); admin queue + status/priority/assignment | B / A |
| Notifications | `GET /notifications`, mark read/read-all | B |
| Customer disputes | `POST/GET /disputes`, `GET /disputes/{id}`, messages (`Idempotency-Key`) | B, owner-scoped |

No endpoint documented in `docs/api.md` is missing from source; `api.md` predates the hotels/restaurants/support/notifications routers (stale by omission). `app/pitstops/` is an empty package.

### 3.2 Authentication & authorization — class 1 with two notable gaps

- **JWT verification**: per-request `GET {SUPABASE_URL}/auth/v1/user` with publishable-or-anon key + Bearer token (`app/auth/service.py:29-35`). No token ever logged; transport errors sanitized.
- **Roles**: customers have no role claim — ownership is enforced by `user_id` in SQL. Vendors resolved via `vendors.owner_id`. Admins are DB rows (`admin_users` + `admin_role_permissions`); `require_permission(p)` is a frozenset check (`app/admin/auth.py:46-51`). 31 permissions, 5 roles, SUPER_ADMIN bootstrap + last-admin/self-disable protections.
- **Org boundaries**: owner-scoped SQL verified across bookings, vendors, slots, support, disputes, checkout verify (`user_owns_payment_order` across all three payment tables), driver trips. Cross-tenant access returns 403/404, not data.
- **Gaps**:
  1. `POST /bookings` has **no Idempotency-Key** and no DB unique guard on (user, slot) — concurrent duplicates possible if the Redis lock elapses (`app/bookings/router.py:73-107`). *(hotels/restaurants/vehicles/trips/disputes/support all have idempotency keys; charging bookings are the exception)*
  2. Multi-vendor accounts: `_vendor_id` silently picks the first vendor (`app/vendors/portal_router.py:26-30`) — latent ambiguity, not cross-tenant exploitable.
  3. Admin RLS (`is_platform_admin()` JWT claim) and API RBAC (`admin_users`) are two parallel systems kept in sync manually.

### 3.3 Booking workflow — class 1 core, gaps in edges

1. **Lock**: Redis `SET NX EX 300` on `{prefix}voltstop:booking-lock:{slot_id}` with random token; release via compare-and-delete Lua (`app/bookings/router.py:43-61`).
2. **Create**: lock ownership verified with `secrets.compare_digest`; Razorpay order created server-side; then `create_pending_booking` in one transaction: `SELECT ... FOR UPDATE OF cs` on the slot, vendor verified/active, server price == client price, active-booking count vs capacity, slot flips to `booked` when full (`app/core/database.py:1217-1278`). **Overbooking is guarded at SQL level.**
3. **Capture**: webhook and checkout-verify converge on `process_payment_webhook` (`database.py:1462-1567`): row locks in consistent order, order/payment pairing + currency + exact paise amount re-verified, `UniqueViolationError` on `razorpay_payment_id` as final race guard. Captured → booking `pending→confirmed`; failed → `expired` + capacity release.
4. **State machine**: `pending → confirmed | expired | cancelled`; `confirmed → completed` (vendor accept→complete, requires webhook-verified capture). Vendor acknowledgement tracked separately.
5. **Gaps**:
   - **No pending-booking expiry sweep for charging bookings** — an abandoned checkout holds capacity until a failed-payment webhook or manual cancel. (Hotels have a lazy `_expire_pending` sweep, `hotels/repository.py:50-70`; restaurants expire lazily too.)
   - No `reconciliation_required` state when Razorpay order creation times out mid-request (hotels/restaurants have it; charging does not).
   - No idempotency key (§3.2).

### 3.4 Payments — class 1 verified on staging, refunds class 2

- `RazorpayGateway` (`app/payments/service.py`): create order (mode/key-prefix consistency, response validation), fetch payment. Capture happens **only** via webhook state transitions.
- Webhook: raw-body HMAC-SHA256 vs secret, constant-time compare; handles `payment.captured/failed`, `refund.created/processed/failed`; unknown events acked; hotel/restaurant handlers fall back on the same endpoint (`app/payments/router.py:75-151`).
- Checkout verify: client signature check (key secret) → ownership → live provider fetch → same capture path. Client callbacks are never trusted alone.
- Uncertain refund submissions held in `processing` with `provider_status=response_unknown`, requiring manual reconciliation (`app/admin/refund_service.py:40-48`). No background reconciler.
- Staging evidence: order → checkout → signature verify → captured, booking `confirmed`, `amount_paid=50.00` (phase-30 smoke). **Webhook delivery itself is unverified anywhere** — `RAZORPAY_WEBHOOK_SECRET` is intentionally unset in staging; production unknown.
- Gap: no DB constraint enforcing one-active-refund-per-payment (API checks in queries; concurrent approvals could race).

### 3.5 Cancellation & refunds — class 1 (charging/hotel), gaps elsewhere

- Policy: `POLICY_VERSION="2026-10-20-v1"` — ≥48h 100%, 24–48h 90%, <24h 50%, at/after start 0%; gateway-fee deduction 0 (`app/core/cancellation_policy.py`).
- Charging cancel: row-locked booking, idempotent by state, policy snapshot (`cancellation_fee_inr`, `refund_amount_inr`, `cancellation_policy_version`, `cancelled_at`), refund row with `customer-cancel:{booking_id}` idempotency key, capacity release if under capacity (`database.py:1371-1460`).
- Hotel cancel: same policy, IST check-in basis, partial-night release logic (`hotels/repository.py:313-374`).
- Admin refunds: request (idempotency-key reuse validation) → approve → `RefundService.issue` (claims `approved→processing` atomically, Razorpay POST with `voltstop_refund_id` note) → webhook completes. Reject supported. Amount validated against captured-minus-reserved.
- **Gaps**: vendor-initiated cancellation **missing** (vendors can only accept/complete); restaurant order cancellation **missing** (no endpoint, no UI); dispute reason codes are free-form strings (no enumerated reason-code list).

### 3.6 Other domains

| Domain | Class | Notes |
|---|---|---|
| Reviews | 4 | No module, no tables, no UI anywhere |
| Support tickets | 1 | Role-aware, idempotent, internal admin notes, audit-logged, DB notifications to requester + support admins |
| Notifications | 1 (DB inbox) / 4 (outbound) | In-app rows only; no email/SMS/push channel exists anywhere in the API; only support flows write rows |
| Analytics | 2 | `/admin/dashboard` and `/admin/analytics` share one read-only query set; no time-series service |
| Driver trips/vehicles | 2 | Backend fully implemented + tested; host DB migration state unverified; discovery is browse-only by design |
| Hotels | 2 | Solid quote/reserve/inventory; 1 failing test (see §6.1); **schema drift bug** (see §4.4) |
| Restaurants | 2 | Pickup-only, no cancellation; payment-gated status transitions |
| Payouts/settlement | 4 | Explicitly not implemented; `/ready` reports `vendor_settlement_transfers=not_configured`; payout pages are estimates |

### 3.7 Ops & security

- **Rate limiting: none** (class 4) — no limiter on auth-verify, webhook, or public endpoints.
- **Security headers: none** (class 4) — no HSTS, X-Content-Type-Options, etc. CORS is a strict explicit allowlist with `allow_credentials=False` (class 1).
- **Input validation**: strong — Pydantic `extra="forbid"`, field constraints, tz-aware datetime requirements on admin filters (class 1).
- **Logging**: clean — no tokens/PII in logs, error codes only, bounded request metadata for audit (class 1).
- **Config**: fail-closed environment validation — staging/prod require explicit HTTPS Supabase, `.supabase.co`/pooler DB with credentials, `rediss://` Redis with password, Razorpay key-prefix/mode match, prod requires webhook secret ≥32 chars (class 1).

### 3.8 Integrations in code

| Integration | Status | Class | Evidence |
|---|---|---|---|
| OSRM routing | Real HTTP per request, public default router, 10s timeout, **no caching/fallback/retry**; pilot-corridor-only (`PILOT_PLACES`) | 1 (works) / 2 (no SLA) | `app/routes/service.py:63-70` |
| Google Routes/Maps | `GoogleRoutesProvider` fully implemented but **never instantiated** — dead code; OSRM always injected | 4 | `app/routes/service.py:94-135`, `routes/router.py:26` |
| Supabase Auth | Public-key REST only (`/auth/v1/user`, `/auth/v1/health`); no service-role, no Admin API in the API | 1 (staging) | `app/auth/service.py` |
| Redis | Booking locks only; key `{REDIS_KEY_PREFIX}voltstop:booking-lock:{slot_id}`; used in bookings, vendor dashboard/availability guards, admin live-operations, readiness | 1 (staging) | `app/core/dependencies.py` |
| Razorpay | Orders + fetch + verify + webhook as above | 1 (staging capture) | `app/payments/service.py` |

---

## 4. Database audit (`supabase/migrations`)

### 4.1 Overview

- **15 migrations** (202610020001 → 202610200001), additive, re-runnable; three safe check-constraint replacements; no table/column drops. 37 tables, **all with RLS enabled**; 20 functions, 24 triggers; no views; no native enums (all `text` + CHECK).
- Seed data: admin roles/permissions matrix (5 roles, 31 permissions), commission settings (500 bps), demo corridor (dev seed only).

### 4.2 Indexes — good coverage, four gaps

Every API hot-path predicate has an index (bookings user/vendor/slot, payments razorpay ids, refunds, disputes, support, hotels, restaurants, driver trips). **Missing (prioritized):**

1. **`refunds.payment_id` — HIGH** — every cancellation, refund approval and refund webhook filters/sums by `payment_id`; grows linearly with refund volume.
2. **`bookings.payment_id` — MEDIUM** — `UNIQUE(id, payment_id)` has `id` leading; webhook payment lookups and the deferrable FK are unindexed.
3. `support_tickets.assigned_to` — MEDIUM (per-agent queues).
4. `restaurant_order_items.item_id`, `notifications.booking_id`, `admin_audit_logs.admin_user_id` — LOW (FK integrity scans).
5. Two redundant indexes (hotel/restaurant `razorpay_order_id` duplicate their UNIQUE constraints).

### 4.3 RLS & security — class 1

- All 37 tables RLS-enabled; owner-scoped policies on profiles/vendors/services/slots/bookings/payments; admin escape hatch via protected JWT claim `app_metadata.role='admin'`; API-only admin tables (refunds, disputes, admin_users, audit logs) have RLS on, policies off, grants revoked — service-role only.
- Defense-in-depth triggers: owner cannot self-verify/activate; non-admin cannot release locked slots or cut capacity below active bookings; audit log, dispute events, support history immutable.
- Nuance: bookings/payments/notifications have table-level write grants to `authenticated` with no matching non-admin write policies — dead surface area (RLS default-deny keeps it safe).

### 4.4 Schema drift bug — class 3 (breaking)

**`hotels/repository.py` and `hotels/schemas.py` reference `hotel_room_types.is_open_24_hours`, `operating_start_time`, `operating_end_time` — but NO migration creates these columns** (grep across all 15 migrations: zero hits). Any create/patch/search room-type call against staging or production will raise undefined-column errors. The vendor web hotel-management UI exposes these fields. **This is the single most concrete bug found in the audit** and must be fixed with a migration (or the fields removed from the API) before hotel management can work.

### 4.5 Other schema notes

- Charging inventory is computed (capacity minus active bookings) under `FOR UPDATE` — correct and atomic.
- Hotel inventory is per-night rows with `rooms_available <= room_capacity` CHECK, decremented in-transaction with row locks.
- `set_updated_at` triggers missing on hotel (6), restaurant (6), and `driver_vehicles` tables — API writes `updated_at` manually (works today, API-dependent).
- No partial-unique "one active refund per payment" constraint (API enforces in queries; race possible on concurrent approvals).
- Service-type vocabulary duplicated across `vendor_services.service_type` (6 values), `charging_slots.service_type` (7 values), and API constants — drift risk.

---

## 5. Mobile app audit (`apps/mobile`)

### 5.1 Structure

Android-only (no `ios/`), v0.1.2+8, branded "DRIVER APP". Plain `Navigator.push` routing (no named routes/deep links). Root gate: splash → onboarding → profile recovery → profile setup → `DriverShell` (4-tab `NavigationBar`: Home, Discovery, Reservations/Trips, Profile).

### 5.2 Feature status

| Area | Class | Notes |
|---|---|---|
| Phone OTP sign-in (Supabase) | 1 | Full flow with `/ready` pre-flight gating so a dead backend never consumes an OTP; 60s resend cooldown; thorough Supabase error mapping |
| Session persistence/logout | 1 | supabase_flutter default persistence; manual logout; no `authChanges` listener |
| Home/discovery | 1 | Real API data (`/routes/plan`, `/vendors/nearby`, `/bookings`) + Supabase realtime; **zero mock data** |
| Search & filters | 2 | Client-side text search + 4 category chips; category not wired to backend query params |
| Map/list | 1 | flutter_map + OSM tiles, real coordinates; labelled schematic corridor fallback when no route coordinates |
| Directions | 2 | Public OSRM called directly from device, gated on location; degrades honestly to "destination shown, no route" |
| Pitstop details | 1 | Charging slots preview, hotel "Choose dates & reserve", restaurant "Browse menu & order" |
| Charging booking + Razorpay | 1 | Lock → review w/ countdown → `POST /bookings` → razorpay_flutter checkout → server verify → poll until confirmed; SDK callbacks treated as non-authoritative |
| Hotel booking | 2 | Complete quote/reserve/pay/poll flow; no staging e2e evidence yet |
| Restaurant ordering | 2 | Full menu/options/cart/pay; **no cancellation** (backend gap) |
| Cancellation + refunds | 2 | Quote→confirm→cancel with refund amounts shown for charging and hotel stays; refund webhook completion unverified live |
| Reviews | 4 | Missing entirely |
| Favourites / recently viewed | 4 | Missing |
| Driver trips | 2 | Create/edit/discover/start/complete/cancel; discovery browse-only ("VoltStop does not book seats or process trip payments") |
| EV charging live status | 5 | No CPO feed — honestly labelled everywhere ("Live connector status unavailable", "does not confirm a charger is free right now") |
| Push notifications | 4 | In-app realtime + foreground geofencing alerts only; no FCM |
| QR gate validation | 4 | QR rendered but labelled "not yet available" — no backend |
| Disputes | 2 | Create/detail reachable from bookings; **list screen is dead code** (unreachable) |
| Profile/vehicles/SOC | 1 | Full garage CRUD, default vehicle, per-vehicle SOC persistence |

### 5.3 Hardcoded values (honest but notable)

- Default Supabase project URL + publishable key compiled in (`app_config.dart:19-30`) — client-safe by design, but production project ID baked into default builds.
- Hardcoded NH-16 town list (9 towns) constrains all origin/destination pickers.
- Discovery fallback coordinates (Andhra Pradesh) when no location; emulator default `10.0.2.2:8000` guarded at build time (app refuses to run without explicit `API_BASE_URL`).

### 5.4 UX quality (see also `voltstop-ux-audit.md`)

- Centralized Material 3 theme tokens (forest `#1A4035`, lime `#B7DC68`, cream `#F4F3EC`), 48px+ tap targets, consistent `VoltLoading`/`VoltError`/empty states on every screen, rich `ApiException` taxonomy with human messages, silent keep-last-data on background refresh failure.
- Weaknesses: no dark mode, no text-scale-aware layouts (one exception), 7–11px labels in places, no offline cache/retry-with-backoff, `usesCleartextTraffic=true` in manifest (dev HTTP), stale golden-test artifacts in `test/failures/`.

---

## 6. Web app audit (`apps/vendor-web`)

### 6.1 Structure & auth

- 46 routes: marketing (`/`), auth (`/login`, `/vendor/login` w/ self-serve signup, `/admin/login`, reset), vendor portal (`/vendor/(protected)/*`, 15 pages), admin (`/admin/(secure)/*`, 22 pages).
- **No middleware, no server-side protection** — guards are client components (`ProtectedPortal`, `AdminGuard`); all data pages are client components fetching from the authenticated API. Frontend checks are UX only; the API is the real boundary (acceptable, but page bundles download to anyone).
- Role detection is **server-authoritative**: `resolveRole()` probes `GET /admin/me` then `GET /vendor/profile` — no JWT claim trust.

### 6.2 Vendor portal — real data, real gaps

| Feature | Class | Notes |
|---|---|---|
| Dashboard metrics | 1 | Server-computed (pending requests, today's bookings, capacity, today's revenue) — no fake numbers |
| Business profile + map picker | 1 | Leaflet drag-pin with geolocation; server + client validation; verification banners |
| Photos | 2 | Single `image_url` text field — no upload, no gallery |
| Operating hours | 2 | Free text at profile level; structured per-service/room only |
| Services + pricing | 1 | CRUD with active toggle, structured open hours |
| Availability slots | 1 | Week calendar CRUD, capacity/price/service, guarded deletes |
| Blackout dates | 4 | Missing entirely |
| Bookings list/accept/complete | 1 | Requests view filters webhook-verified captures; accept gated server-side |
| Vendor cancellation | 4 | Explicit disclaimer: "Rejections and refunds are not enabled by the current booking lifecycle" |
| Offers/promotions | 4 | Missing |
| Revenue | 1 | Real server report; payout labelled estimate; minor hardcoded "5%" copy (server uses `commission_rate_bps`) |
| Disputes/support/notifications | 1 | All wired with Idempotency-Key headers |

### 6.3 Admin panel — class 1 breadth

Vendor onboarding (approve/reject/request_changes/suspend/reactivate with mandatory reason), listing moderation (service publish/unpublish, audited), booking investigation (7 filters + event timeline), refund desk (eligibility → request → approve w/ typed `REFUND` → reject; separate hotel queue), disputes (timeline, resolution actions, embedded refund workflow; **evidence upload not connected**), audit logs viewer, customer records, admin user/role management, platform health (`/admin/settings` live config checks), transactions with 8 filters. All permission-gated server-side (`refunds:create`, `refunds:approve`, `disputes:manage`, `services:manage`, …).

### 6.4 Web UX (see `voltstop-ux-audit.md`)

- Custom in-house component kit (Panel, Button, StatePill, Skeleton, ErrorState, EmptyState, ToastViewport, AdminTable…), consistent usage, skeletons on every query, ErrorState with retry, 10s auto-refresh when visible+online.
- CSS tokens layered three times (dark base in `globals.css` overridden by `portal-refresh.css` light theme and a second admin light block) — fragile. Tailwind v4 installed but **zero utility classes used**.
- Accessibility uneven: aria labels/roles present in places; `:focus-visible` only on nav links/modal cards; admin table typography at 8–10px; no skip links.

---

## 7. Tests, CI, deployment

### 7.1 Test inventory and results (this session)

| Suite | Result | Notes |
|---|---|---|
| Backend pytest (`apps/api/tests/`, 157 tests) | **153 passed, 3 skipped, 1 failed** | Hermetic (in-memory doubles, no DB). Coverage: auth, RBAC matrix, vehicles, vendors, bookings/locks, cancellation policy tiers, Razorpay webhook security (13 tests incl. replay/concurrency), checkout verify, hotels, restaurants, support, disputes, config validation, health sanitization |
| Failing test | `tests/test_hotels.py::test_same_customer_idempotency_key_returns_existing_reservation` | Root cause: `hotels/repository.py:190` checks inventory availability **before** its idempotency-fingerprint lookup — on replay the room is gone, so it 409s instead of returning the existing reservation. Fix: fingerprint check before availability check (or snapshot semantics in the test double) |
| Skipped | 3 integration probes (Supabase/Redis/Razorpay) | Gated by `RUN_INTEGRATION_TESTS=1` — opt-in external requests |
| Web tests | 13/13 pass (`npm run test:supabase-config`) | Supabase env/config/key-classification only |
| Web E2E/component | **none** | No jest/playwright configs anywhere |
| Mobile tests | ~49 Dart tests + goldens | Flutter CLI not on PATH this session; docs record full suite passing 2026-10-11. Stale golden diff artifacts in `test/failures/` |

### 7.2 CI/CD — class 4

- **No GitHub Actions, no CI config of any kind.** No root package.json. Deploys via Vercel Git integration; pre-deploy checks are manual (pytest, `tsc --noEmit`, readiness probe).

### 7.3 Deployment config

- **No `vercel.json` anywhere** — Vercel auto-detect (FastAPI via `apps/api/index.py`; Next.js preset with monorepo `outputFileTracingRoot`).
- Env templates complete and documented (`.env.example` ×2, `.env.integration.example`) with fail-closed validation in code.
- `docker-compose.yml` (Redis + API) is informational only — per project rules, Docker must not become a requirement.
- Operational scripts: `apps/api/scripts/check_staging_readiness.ps1` (read-only probe, passed staging with `-RequirePaymentCheckout`), `scripts/staging_smoke_*.py` (untracked, contain staging credentials — keep out of commits).

### 7.4 Production state — unknown (class 5)

`docs/production-readiness-status.md` (2026-10-14) records the production web and API Vercel deployments **were deleted** and no public production deployment existed at that time. No evidence of a live production deployment exists in this repo today. Production migration ledger, role flows and payment config are unverified.

---

## 8. Integration status matrix (evidence-based)

| Integration | Wired in code | Staging verified | Production |
|---|---|---|---|
| Supabase Auth | Yes | **Yes** (accounts created, OTP-bypass admin create, `auth/verify` 200) | Unknown |
| Supabase Postgres | Yes (validated pooler URL) | **Yes** (15 migrations, booking flow persisted) | Unknown |
| Razorpay checkout + capture | Yes | **Yes** (test-mode order → Netbanking simulator → signature verify → captured) | Unknown |
| Razorpay webhook delivery | Code complete | **No** (secret unset — phase-30 remaining work) | Unknown |
| Redis/Upstash locks | Yes | **Yes** (`/ready` reachable, lock held during smoke) | Unknown |
| OSRM routing | Yes (public default) | Not exercised in smoke | Unknown |
| Google Maps/Routes | Code present, unwired | Not configured | Unknown |
| OTP/SMS delivery | Via hosted Supabase Auth | Unverified (Twilio error 21704 asserted in docs, never confirmed) | Unknown |
| Push notifications | Not implemented | n/a | n/a |
| Vendor payouts | Not implemented (estimates only) | n/a | n/a |
| Charger/CPO live feed | No integration exists | n/a | n/a |

---

## 9. Known issues inventory (from code + docs)

1. **Schema drift**: `hotel_room_types` operating-hours columns referenced by API but absent from migrations (breaking).
2. Failing test: hotel reservation idempotent replay (root cause identified).
3. Charging pending-bookings never expire automatically.
4. `POST /bookings` lacks idempotency key + reconciliation state.
5. No one-active-refund-per-payment DB guarantee.
6. Missing `refunds.payment_id` index (hot path).
7. Webhook delivery unverified (secret unset in staging, unknown in production).
8. No CI/CD; no rate limiting; no security headers; no load tests; no alerting/runbooks; no backup-restore drills.
9. Exposed credentials in past conversation + untracked smoke scripts (P0 rotation outstanding per prior audits).
10. Production deployments deleted 2026-10-14; current production state unknown.
11. Mobile: no release signing configured; on-device payment behavior unverified; no iOS; `usesCleartextTraffic=true`.
12. Google Routes dead code; OSRM public endpoint without SLA.
13. Vendor-initiated cancellation, restaurant cancellation, blackout dates, offers, reviews, favourites, push notifications, evidence upload — missing (product gaps).
14. Uncommitted `redis_key_prefix` staging-isolation change — complete and consistent in code, not committed, not in local `.env`.

---

## 10. Classification summary

| Layer | Implemented+verified (1) | Incomplete (2) | Broken (3) | Missing (4) | Blocked (5) |
|---|---|---|---|---|---|
| Backend | Auth/authz, booking lock+allocation, payment capture, cancellation (charging/hotel), disputes, support, config validation | Pending-booking expiry, refunds e2e, hotels, restaurants, analytics | 1 failing test (hotel replay) | Reviews, rate limiting, security headers, payouts, outbound notifications, booking idempotency | — |
| Database | RLS, indexes, constraints, migration hygiene | updated_at triggers, refund-active constraint | hotel operating-hours drift | views (unneeded) | — |
| Mobile | OTP auth, booking+payment, discovery, cancellation UI, vehicles | Search filters, directions, hotel/restaurant e2e, disputes list | golden-test artifacts | Reviews, favourites, push, iOS, QR backend | Live charger feed |
| Web | Vendor portal + admin breadth, real data, auth probing | Photos, hours, refund pipeline, payouts | — | Blackout dates, offers, vendor cancel, evidence upload, UI tests | — |
| Ops | Env validation, readiness probe, smoke scripts | — | — | CI/CD, rate limits, headers, load/alerting | Production deployment evidence, webhook delivery, OTP delivery |
