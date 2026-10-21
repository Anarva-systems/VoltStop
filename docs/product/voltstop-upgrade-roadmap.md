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
- Uncommitted work exists: the `redis_key_prefix` staging-isolation change (complete, consistent) and staging smoke scripts (contain credentials — keep untracked). Both must be handled explicitly in batch 1.

---

## 1. Batch 0 — Fix the money-path and platform basics (Phase 3, ~1–2 sessions)

Highest-priority, well-understood fixes with concrete root causes. **Do these before any visual work.**

| # | Item | Type | Evidence |
|---|---|---|---|
| 0.1 | **Hotel operating-hours schema drift**: add migration for `hotel_room_types.is_open_24_hours / operating_start_time / operating_end_time` (or remove the fields from `hotels/schemas.py` + `hotels/repository.py` + vendor web UI) | Bug fix | API references columns that no migration creates — any hotel room-type call raises undefined-column errors |
| 0.2 | Fix failing test `test_hotels.py::test_same_customer_idempotency_key_returns_existing_reservation` — move fingerprint/idempotency lookup **before** inventory availability check in `hotels/repository.py` | Bug fix | Replay hits `ROOM_UNAVAILABLE` because availability is checked first |
| 0.3 | Add `refunds(payment_id)` index (ideally `(payment_id, status)`) via new migration | Perf | Cancellation/approval/webhook paths all filter/sum by `payment_id` |
| 0.4 | Charging pending-booking expiry: lazy sweep (mirror hotels' `_expire_pending`) + optional TTL-based release, releasing capacity and marking `expired` | Reliability | Abandoned checkouts hold capacity indefinitely |
| 0.5 | `POST /bookings`: require `Idempotency-Key` (fingerprint + unique constraint like restaurants) and add `reconciliation_required` handling when Razorpay order creation fails mid-request | Reliability | Duplicate bookings possible after lock expiry; no reconciliation state |
| 0.6 | One-active-refund-per-payment DB guarantee (partial unique index on non-terminal statuses for `refunds` and `hotel_refunds`) | Reliability | Concurrent refund approvals can race |
| 0.7 | Rate limiting (slowapi or equivalent): `/auth/verify`, `/payments/razorpay/webhook` (per IP), public vendor endpoints, booking/lock | Security | No rate limiting exists anywhere |
| 0.8 | Security headers middleware (HSTS, X-Content-Type-Options, Referrer-Policy, nosniff) | Security | None exist beyond CORS allowlist |
| 0.9 | CI workflow (GitHub Actions): backend pytest + web tsc/tests + flutter analyze on push/PR | Ops | No CI exists |
| 0.10 | Commit the `redis_key_prefix` change; remove staging credential files from the repo working area (keep locally, add `.gitignore`) | Hygiene | Uncommitted, complete; smoke scripts hold staging secrets |

**Verification:** 157/157 backend tests green (after 0.2); new tests for 0.4–0.6 (expiry, idempotent booking, concurrent refunds); staging redeploy; readiness probe still passes.

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
