# VoltStop — Upgrade Roadmap

**Date:** 2026-10-21
**Basis:** `voltstop-current-state-audit.md`, `voltstop-feature-gap-matrix.md`, `voltstop-ux-audit.md`
**Strategy:** reliability first, then design system, then feature completion — in small, testable batches. Preserve the working product; never replace real functionality with static mockups; never claim unverified integrations.

---

## 0. Principles & constraints

- Work in the existing architecture (FastAPI + Next.js 15 + Flutter + Supabase + Razorpay). No rewrites.
- No Docker as a requirement. No privileged keys in frontend bundles.
- No destructive DB changes or production migrations without: confirmed target database, verified backup, explicit approval.
- Every batch: run `pytest` (apps/api), `tsc --noEmit` + `test:supabase-config` (apps/vendor-web), `flutter analyze test` where toolchain allows; fix regressions introduced.
- External claims need evidence: webhook delivery, OTP delivery, production deployment are currently **unverified** — items that depend on them stay marked "blocked" until evidence exists.
- The `redis_key_prefix` staging-isolation change and staging smoke-script hygiene are **resolved and committed** (2026-10-21): prefix config committed, credential scripts gitignored, no credentials ever reached the remote (verified via `git log --all` and `git ls-tree origin/main`). See Batch 0.11.

---

## 1. Batch 0 — Fix the money-path and platform basics (Phase 3, ~1–2 sessions)

**Status: DONE (2026-10-21).** All items implemented, tested, and committed locally (commits `33706a9`..`05cd99d` + CI/hygiene commits on `main`, not pushed). Migrations applied to staging Supabase only.

| # | Item | Result | Evidence |
|---|---|---|---|
| 0.1 | Hotel operating-hours schema drift | Fixed via migration `202610210001_hotel_room_operating_hours.sql` (additive `if not exists` + check constraint), applied to staging (18/18 migrations recorded) | Migration test asserts additive statements only; backend suite green |
| 0.2 | Hotel reservation idempotency replay | Verified correct: replay lookup already precedes inventory check; fixed the test double that mis-stored rows | `test_hotels.py::test_same_customer_idempotency_key_returns_existing_reservation` passes |
| 0.3 | Refund `payment_id` lookup index | `202610210002_refund_integrity_indexes.sql` — partial unique `(payment_id) where status not in ('failed','rejected')` on `refunds` and `hotel_refunds`; serves lookup and the one-open-refund invariant | Applied to staging; 3/3 new indexes present (verified via `pg_indexes`) |
| 0.4 | Charging pending-booking expiry | Lazy `_expire_pending_bookings` sweep (`for update skip locked`) on every booking path; expires stale `pending` holds, releases slot capacity, records `booking_events.expired`; `hold_expires_at` set at creation from lock TTL | Unit-tested sweep + capacity release in `test_charging_booking_reliability.py` |
| 0.5 | Booking idempotency + reconciliation | `idempotency_key` (server-derived from single-use lock token) + `request_fingerprint` (hashed payload) + `unique(user_id, idempotency_key)`; fingerprint mismatch → 409 `IDEMPOTENCY_KEY_REUSED`; replay returns the existing booking; payments get `order_state` (`creating → ready / reconciliation_required`); gateway failure marks reconciliation and retry returns 503 `PAYMENT_RECONCILIATION_REQUIRED` | 4 dedicated tests incl. replay, fingerprint conflict, attach/unknown transitions |
| 0.6 | One-active-refund DB guarantee | Covered by 0.3's partial unique indexes (fail-loud on violating data, documented in the migration comment) | Migration test + existing refund state-machine tests |
| 0.7 | Rate limiting | New `app/core/rate_limit.py`: Redis Lua fixed-window with in-process fallback, fail-open on Redis errors. Applied to `/auth/verify` (30/min), booking lock (20/min) and create (10/min), `/vendors/nearby` (60/min), webhook (300/5min). Keys namespaced by `redis_key_prefix` | `test_rate_limit.py`: limit enforced, prefix isolation, fail-open |
| 0.8 | Security headers | Pure-ASGI middleware inside the CORS wrapper: nosniff, frame-DENY, no-referrer, permissions policy; HSTS only over HTTPS (local HTTP unaffected) | `test_security_headers.py` covers HTTP + HTTPS paths |
| 0.9 | CI workflows | `.github/workflows/`: backend pytest (3.12), web tsc + supabase-config tests (Node 22), Flutter analyze/test (stable channel, `flutter-action`) | Backend + web commands run locally with identical invocations; Flutter not verifiable locally (no Flutter CLI) — first CI run needs monitoring |
| 0.10 | Redis prefix commit + credential hygiene | `redis_key_prefix`/`booking_lock_prefix` committed (`33706a9`); root `.gitignore` excludes `scripts/` credential files; verified nothing credential-bearing ever reached git history or the remote | `git ls-tree origin/main` shows only the committed readiness probe |

**Verification:** backend 168 passed / 3 skipped / 0 failed; web `tsc --noEmit` clean + 13/13 supabase-config tests; 3 migrations parsed (pglast) and applied to staging; staging API redeployed from local code via Vercel CLI. Remaining evidence in flight: staging smoke of booking → payment → capture against the redeployed API.

## 2. Batch 1 — Verify the payment pipeline live (Phases 3–4, requires user/config)

Blocked until user action — flag, don't fake:

| # | Item | Blocker |
|---|---|---|
| 1.1 | Configure Razorpay webhook endpoint on staging, set `RAZORPAY_WEBHOOK_SECRET` in staging API env, re-run readiness probe with `-RequireWebhook` | Razorpay dashboard access |
| 1.2 | Staging e2e: webhook-driven capture (not checkout-verify), refund `requested→completed` via webhook, failed-refund webhook, duplicate webhook replays | Depends on 1.1 |
| 1.3 | Cancellation boundary e2e on staging (49/48/24/1/0h tiers, duplicates, refund statuses) | Depends on 1.1–1.2 |
| 1.4 | Decide + execute production redeployment (deployments were deleted 2026-10-14; ledger/role/payment config unverified) | User decision — production scope |

## 3. Batch 2 — Design system foundation (Phase 2, before any screen redesign)

| # | Item | Surface |
|---|---|---|
| 2.1 | Consolidate web tokens: one palette (`:root` variables), delete layered `portal-refresh.css`/`admin.css` overrides; document token spec in `docs/product/` | Web |
| 2.2 | Component pass: buttons, inputs, cards, tables, dialogs, status badges — focus-visible everywhere, 12px+ minimum table text, consistent radii/elevation | Web |
| 2.3 | Mobile token audit: extract remaining hardcoded colors/sizes into `app_theme.dart`; add text-scale-aware layouts; add dark mode | Mobile |
| 2.4 | Web route-level `loading.tsx` / `error.tsx` / `not-found.tsx` | Web |
| 2.5 | Field-level validation errors on web forms | Web |
| 2.6 | Remove dead code (`DisputesScreen` mobile, `/admin/complaints` duplication, informational `/admin/routes`) after confirming no references | Both |

**Verification:** visual check in browser on staging web; golden tests where applicable; `tsc`/`flutter analyze` clean.

## 4. Batch 3 — Screen redesigns in priority order (Phase 2)

Apply the design system surface-by-surface; each lands with its tests:

1. **Customer home & discovery** (mobile Home + Discovery, marketing page touch-up)
2. **Search, filters, map/list** — wire category filters to backend query params (`/vendors/nearby` accepts service_type), search suggestions from catalog
3. **Details** (pitstop / hotel / restaurant) — unify card layout, status badges, cancellation terms placement
4. **Booking, checkout, confirmation** — lock countdown, payment states, honest status copy preserved
5. **Booking history, cancellation, refunds** — refund status visibility for customers (currently partial)
6. **Vendor dashboard, listing editor, booking calendar** — week calendar polish, photo placeholder handling
7. **Admin operations, verification, investigation** — filter bar consistency, table density fix

Each batch must keep: real API data only, skeletons/error/empty states, honest capability labels.

## 5. Batch 4 — Cancellation & refund engine completion (Phase 4)

Most of the engine exists and is tested. Close the gaps:

| # | Item | Notes |
|---|---|---|
| 4.1 | Vendor-initiated cancellation (with policy-compliant fees, refund flow, portal UI replacing the current disclaimer) | New endpoint + portal page; fits existing state machine |
| 4.2 | Restaurant order cancellation (pre-acceptance window; quote + refund reuse of hotel/charging pattern) | Decide policy window with user first |
| 4.3 | Enumerated dispute reason codes (replace free-form) + evidence upload storage (Supabase Storage) wired to admin dispute detail | Storage bucket + signed-URL flow |
| 4.4 | Background reconciliation of `processing`/`response_unknown` refunds (cron or on-read check) | Respect provider contract; never mark complete without provider evidence |

## 6. Batch 5 — Vendor & admin improvements (Phase 5)

| # | Item | Notes |
|---|---|---|
| 5.1 | Blackout dates for services/slots (schema + portal UI) | Closes per-slot workaround |
| 5.2 | Photo upload (Supabase Storage) + gallery, replacing single `image_url` field | Signed uploads; admin moderation view |
| 5.3 | Operating-hours consolidation (fix drift from 0.1, then structured hours everywhere) | Depends on 0.1 |
| 5.4 | Offers/promotions (vendor-defined discounts applied at checkout, server-priced) | New schema + quote path change; small scope first |
| 5.5 | Revenue report copy fix (use server `commission_rate_bps` instead of hardcoded "5%") | Trivial |
| 5.6 | Admin: settlement/payout readiness view (still estimates — no money movement without a separate payment-provider contract) | Honest labelling preserved |

## 7. Batch 6 — Customer experience & growth (Phase 6)

| # | Item | Priority | Notes |
|---|---|---|---|
| 6.1 | Favourites + recently viewed (local-first, then server persistence) | High | Simple, high perceived value |
| 6.2 | Verified reviews (post-completed-booking gating, moderation queue, average ratings on listing cards) | Medium | New schema + admin moderation |
| 6.3 | Mobile support UI (API is complete; no mobile surface exists) | High | Reuse web patterns |
| 6.4 | Push notifications (FCM) for booking/status events — **requires user-provided Firebase project** | Medium | Blocked item; in-app realtime already covers core |
| 6.5 | Booking reminders (in-app first; email via Supabase Auth templates later) | Low | |
| 6.6 | Referrals (single-code, first-booking reward) | Low | Needs finance/policy decision |
| 6.7 | Driver trip enhancements (discover filters, matching to passenger demand **only as a separately specified workflow** — no seat payments/ride-sharing obligations without explicit design) | Low | Existing model is browse-only; do not silently extend |
| 6.8 | EV charging: keep static info static; only add live availability with a real CPO/OCPP source | Blocked | Never fabricate live data |

## 8. Batch 7 — Security, performance & testing (Phase 7)

| # | Item |
|---|---|
| 7.1 | Expand test suites: booking races (0.5), webhook retries, cancellation deadlines/fees, role isolation for new endpoints, web component tests (jest/playwright), mobile widget tests for redesigned screens |
| 7.2 | Load/concurrency test on staging (bookings + webhook bursts) |
| 7.3 | Query performance review (EXPLAIN on hot paths after index additions) |
| 7.4 | Image loading (responsive sizes, lazy load, WebP) |
| 7.5 | Backup/restore drill on staging Supabase + runbook |
| 7.6 | Operational alerts (Vercel logs, Supabase health, Razorpay webhook failures) |
| 7.7 | Mobile release signing configuration + production build |
| 7.8 | Secrets rotation for exposed credentials (documented P0 from prior audits) |

## 9. Blocked / decision-needed register

| Item | Needed from user | Until then |
|---|---|---|
| Webhook e2e (1.1) | Razorpay dashboard config + secret in staging env | Refund/cancellation live verification stays unproven |
| Production redeployment (1.4) | Go decision + prod env values | Production state stays unknown |
| Push notifications (6.4) | Firebase project | In-app realtime remains the channel |
| OTP/SMS delivery verification | Supabase Auth provider check (Twilio 21704 unresolved) | Claim stays unverified |
| Google Routes activation (optional) | API key decision | OSRM stays primary |
| Vendor settlement/payouts | Payment-provider contract + legal | Estimates only |
| Live charger availability | CPO/OCPP source | Static listings only, honestly labelled |
| Mobile store release | Signing keystore + store accounts | Local builds only |

## 10. Definition of done (per batch)

1. Tests added/updated and green (`pytest`, `tsc`, web tests, flutter where available)
2. Staging redeployed and probe/smoke passed where behavior changed
3. No regression in existing smoke flow (booking → payment → capture)
4. Docs updated (`docs/product/*` + relevant `docs/*.md`)
5. Report: exact files changed, features implemented, tests run/passed, unresolved risks, external configuration required, deployment steps — with locally verified results separated from unverifiable production behavior
