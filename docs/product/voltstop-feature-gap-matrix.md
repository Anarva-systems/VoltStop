# VoltStop — Feature Gap Matrix

**Date:** 2026-10-21
**Companion to:** `voltstop-current-state-audit.md` (evidence) and `voltstop-upgrade-roadmap.md` (sequencing)

Status key: **1** implemented + verified · **2** implemented, incomplete · **3** present but broken · **4** missing · **5** blocked by unavailable integration/credential

---

## 1. Core booking & payments

| Feature | API | DB | Mobile | Web | Admin | Overall | Evidence / notes | Priority |
|---|---|---|---|---|---|---|---|---|
| Slot discovery (nearby vendors, slots) | 1 | 1 | 1 | — | 1 | 1 | `/vendors/nearby` + `/vendors/{id}/slots`; indexes on location/slot time | — |
| Slot locking (Redis, 300s TTL) | 1 | — | 1 | — | — | 1 | `SET NX EX`, Lua compare-delete release; staging smoke | — |
| Atomic capacity allocation (no overbooking) | 1 | 1 | — | — | — | 1 | `FOR UPDATE` + count + `booked` flip; test `test_api.py:1209-1248` | — |
| Booking creation + server-priced Razorpay order | 1 | 1 | 1 | — | — | 1 | Staging capture verified end-to-end | — |
| Booking idempotency key | 1 | 1 | — | — | — | 1 | **Fixed 2026-10-21:** server-derived key from single-use lock token + `unique(user_id, idempotency_key)`; fingerprint mismatch → 409; live concurrent-create race returned the fail-safe 503 (no duplicate) | — |
| Pending-booking auto-expiry (charging) | 1 | 1 | — | — | — | 1 | **Fixed 2026-10-21:** lazy `for update skip locked` sweep on all booking paths; `hold_expires_at` from lock TTL | — |
| Order-creation failure reconciliation state | 1 | 1 | — | — | — | 1 | **Fixed 2026-10-21:** `payments.order_state` `creating → ready / reconciliation_required`; gateway failure marks unknown; replay returns 503 | — |
| Payment capture (webhook-authoritative) | 1 | 1 | — | — | — | 1 | 13 security tests incl. replay/concurrency | — |
| Webhook delivery verified live | 2 | — | — | — | — | 5 | Secret unset in staging; never exercised against provider | **P0** (config) |
| One-active-refund-per-payment guarantee | 1 | 1 | — | — | — | 1 | **Fixed 2026-10-21:** partial unique indexes `refunds_payment_open_idx` / `hotel_refunds_payment_open_idx` (fail-loud on violating data) | — |
| Manual refund reconciliation state | 2 | — | — | — | 2 | 2 | `processing`/`response_unknown` held; no background reconciler | P2 |

## 2. Cancellation & refunds

| Feature | API | DB | Mobile | Web | Admin | Overall | Evidence / notes | Priority |
|---|---|---|---|---|---|---|---|---|
| Cancellation policy (100/90/50/0 tiers) | 1 | 1 | 1 | — | — | 1 | `cancellation_policy.py` + 5 boundary tests; snapshot columns on bookings/reservations | — |
| Policy shown pre-checkout + in details | 1 | — | 1 | — | — | 1 | BookingReview copy matches policy; web booking detail shows refund status | — |
| Customer cancel — charging | 1 | 1 | 1 | — | — | 1 | Idempotent-by-state, fee/refund snapshot, capacity release | — |
| Customer cancel — hotel | 1 | 1 | 1 | — | — | 2 | Implemented + partial-night logic; no live staging e2e yet | P2 |
| Customer cancel — restaurant orders | 4 | 4 | 4 | 4 | — | 4 | No endpoint, no UI | P1 |
| Vendor-initiated cancellation | 4 | — | — | 4 | — | 4 | Vendors can only accept/complete; portal discloses this | P1 |
| Admin refund request/approve/reject | 1 | 1 | — | 1 | 1 | 2 | Full chain to Razorpay; webhook completion unverified live | P1 |
| Refund status tracking (requested→completed/failed) | 1 | 1 | 2 | 1 | 1 | 2 | States exist; customer visibility partial | P2 |
| Duplicate refund/cancellation prevention | 1 | 2 | — | — | — | 2 | Idempotency keys + state checks; missing DB-level active-refund guard | P1 |
| Disputes + reason codes + audit | 1 | 1 | 2 | 2 | 1 | 2 | Full workflow; reason is free-form text (no enumerated codes); evidence upload not connected; mobile list dead code | P2 |

## 3. Vendor capabilities

| Feature | API | DB | Mobile | Web | Admin | Overall | Evidence / notes | Priority |
|---|---|---|---|---|---|---|---|---|
| Profile/listing editor (name/type/address/coords) | 1 | 1 | — | 1 | 1 | 1 | Leaflet map picker; staging smoke created real profile | — |
| Photos management | 2 | 1 | — | 2 | — | 2 | Single `image_url` field only; no upload/gallery | P2 |
| Operating hours | 2 | 2 | — | 2 | — | 2 | Profile free-text; structured per-service/room; **hotel room-type hour columns added by migration 202610210001 (2026-10-21, applied to staging)** | — |
| Services catalogue + pricing | 1 | 1 | — | 1 | 1 | 1 | CRUD, active toggle, admin moderation | — |
| Availability slots CRUD + capacity | 1 | 1 | — | 1 | 1 | 1 | Week calendar; guarded deletes; staging smoke | — |
| Blackout dates | 4 | 4 | — | 4 | — | 4 | Workaround: close individual slots | P2 |
| Booking calendar/list + accept/complete | 1 | 1 | — | 1 | 1 | 1 | Gated on webhook-verified capture | — |
| Vendor cancellation | 4 | — | — | 4 | — | 4 | Explicitly not enabled | P1 |
| Offers/promotions | 4 | 4 | 4 | 4 | — | 4 | No coupon/discount model anywhere | P3 |
| Revenue reports | 1 | 1 | — | 1 | 1 | 2 | Real server report; payout estimate only; hardcoded "5%" copy | P2 |
| Hotel room + inventory management | 1 | 1 | — | 2 | 2 | 2 | CRUD + dated inventory wired; **schema drift fixed 2026-10-21 (migration 202610210001 applied to staging)** | — |
| Restaurant menu + order management | 1 | 1 | — | 1 | 1 | 2 | Status transitions payment-gated; no cancel | P1 |
| Disputes/support/notifications | 1 | 1 | — | 1 | 1 | 1 | All wired with idempotency | — |

## 4. Admin capabilities

| Feature | API | DB | Web | Overall | Evidence / notes | Priority |
|---|---|---|---|---|---|---|
| RBAC (5 roles, 31 permissions, server-enforced) | 1 | 1 | 1 | 1 | Permission matrix tested; UI buttons gated | — |
| Vendor onboarding + verification actions | 1 | 1 | 1 | 1 | Approve executed live in staging smoke | — |
| Listing moderation (services) | 1 | 1 | 1 | 1 | Audited publish/unpublish + price edits | — |
| Booking investigation | 1 | 1 | 1 | 1 | 7 filters, event timeline, payment state | — |
| Refund oversight | 1 | 1 | 1 | 2 | Full chain wired; live completion unverified | P1 |
| Disputes management | 1 | 1 | 1 | 2 | Actions + embedded refunds; evidence upload missing | P2 |
| Audit logs | 1 | 1 | 1 | 1 | Immutable, entity/action filters | — |
| Platform health/transactions | 1 | 1 | 1 | 1 | `/admin/settings` live checks; 8-filter transactions | — |
| Customer records | 1 | 1 | 1 | 1 | Cross-entity detail modal | — |
| Payouts execution | 4 | 4 | 2 | 4 | Estimates only; explicitly not implemented | P3 |
| Admin user/role management | 1 | 1 | 1 | 1 | Role + active edit with reason | — |

## 5. Customer experience (mobile-first)

| Feature | API | Mobile | Web | Overall | Evidence / notes | Priority |
|---|---|---|---|---|---|---|
| Phone OTP sign-in | 1 | 1 | — | 1 | `/ready` pre-flight gating; SMS delivery itself unverified (5) | P1 (verify) |
| Home + discovery | 1 | 1 | 1 (marketing) | 1 | Real API + realtime; no mock data | — |
| Search & filters | 2 | 2 | — | 2 | Client-side only; category chips not backend params | P1 |
| Map & list views | 1 | 1 | — | 1 | OSM/flutter_map; labelled schematic fallback | — |
| Directions/routing | 2 | 2 | — | 2 | Public OSRM, no SLA; pilot corridor only | P2 |
| Details (pitstop/hotel/restaurant) | 1 | 1 | — | 1 | All three variants complete | — |
| Booking + checkout + confirmation | 1 | 1 | — | 1 | Staging-verified capture | — |
| Booking history | 1 | 1 | — | 1 | Upcoming/Completed/Cancelled + hotel stays | — |
| Cancellation + refund visibility | 1 | 1 | — | 2 | Quote→confirm→cancel with amounts | P2 |
| Reviews (verified-purchase) | 4 | 4 | 4 | 4 | No model/endpoint/UI | P2 |
| Favourites / recently viewed | 4 | 4 | — | 4 | No persistence | P2 |
| Support tickets | 1 | 4 | 1 | 2 | API + web complete; **no mobile support UI** | P1 |
| Notifications (in-app) | 1 | 1 | 1 | 1 | DB inbox + realtime | — |
| Push notifications | 4 | 4 | — | 4 | No FCM; foreground geofence alerts only | P2 |
| Driver trips (schedule/discover) | 1 | 2 | — | 2 | Browse-only discovery by design; NH-16 town list only | P2 |
| EV journey planning | 2 | 2 | — | 2 | Route energy estimates real; corridor-limited | P2 |
| EV live charger availability | 5 | 5 | — | 5 | No CPO feed; honestly labelled everywhere | P3 (blocked) |
| Referrals | 4 | 4 | 4 | 4 | Not present | P3 |

## 6. Platform & operations

| Feature | Status | Evidence / notes | Priority |
|---|---|---|---|
| CI/CD pipeline | 2 | **Added 2026-10-21:** 3 GitHub Actions workflows (backend pytest, web tsc+tests, Flutter analyze/test); backend+web commands verified locally with identical invocations; first GitHub-runner execution pending (workflows not yet pushed) | — |
| Rate limiting | 1 | **Added 2026-10-21:** Redis fixed-window (Lua) with in-process fallback, fail-open; auth-verify 30/min, booking lock 20/min + create 10/min, vendor discovery 60/min, webhook 300/5min; keys prefixed by `redis_key_prefix` | — |
| Security headers (HSTS etc.) | 1 | **Added 2026-10-21:** ASGI middleware in CORS wrapper; nosniff/DENY/no-referrer/permissions-policy always, HSTS over HTTPS only; verified live on staging responses | — |
| Webhook delivery verification | 5 | Secret unset staging; unknown production | **P0** (config) |
| Production deployment | 5 | Deleted 2026-10-14; no live evidence; ledger unverified | **P0** (decision) |
| Load/concurrency testing | 4 | None | P2 |
| Alerting/runbooks | 4 | None | P2 |
| Backup/restore drill | 4 | Supabase managed; no drill evidence | P2 |
| Secrets hygiene | 2 | **2026-10-21:** credential-bearing smoke files gitignored; verified via `git log --all` + `git ls-tree origin/main` that none ever reached the repo or remote; staging-only creds (smoke users, DB password already rotated once, short-lived tokens). Remaining: revoke any long-lived Supabase token that may have existed in the local `supabase-token.bin` | P1 |
| Test coverage — backend | 1 | 168 pass / 0 fail / 3 skipped (2026-10-21) | — |
| Test coverage — web UI | 4 | No jest/playwright | P1 |
| Test coverage — mobile | 2 | ~49 tests, previously green; Flutter CLI needed; stale goldens | P2 |
| Accessibility | 2 | Uneven focus states, 8–10px admin text, no skip links | P1 |
| Design system | 2 | Per-platform tokens; no shared system; Tailwind unused on web | P1 |
| Google Routes | 4 | Code present, never wired | P3 |
| OSRM SLA | 2 | Public router, no caching/fallback | P2 |
