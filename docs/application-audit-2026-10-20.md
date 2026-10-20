# VoltStop application audit — 20 October 2026

## Scope and confidence

This is a focused repository review of booking cancellation/refunds, the driver directions screen, payment configuration, the existing product-readiness audit, and release/build artifacts. It does not establish production database migration state or prove live Razorpay, SMS, charger-provider, push, backup, load, or on-device behavior. Findings below distinguish code-visible behavior from items that still need staging/production verification.

Static verification for this change: Python syntax compilation and vendor-web TypeScript (`npm run lint`) passed; Dart formatting completed. Flutter analysis did not complete within the available time and was stopped. Automated tests and live payment/database flows were not run.

## Executive assessment

VoltStop has a functioning multi-surface foundation: Flutter driver app, partner/admin web portal, FastAPI API, PostgreSQL data, Supabase identity, and Razorpay payment/refund integration. It is not enterprise-ready for general customer payments yet. The largest blockers are production verification of cancellation/refund operation, payment webhook and refund reconciliation, live charger data, and insufficient staging/device/operational verification.

## P0 — Cancellation and partial-refund policy (approved for now; implementation added locally)

- The user approved this temporary schedule for hotel reservations and charging bookings: 48+ hours before service = 100% refund; 24–48 hours = 90%; under 24 hours = 50%; at/after service start = no refund. No additional gateway-fee deduction is applied. The retained balance is the cancellation amount.
- API changes now expose ownership-scoped cancellation-quote endpoints and recalculate the quote inside the cancellation transaction. Captured verified payments create an idempotent partial refund request for finance review; the API does not promise an immediate/automatic refund. Pending unpaid reservations cancel with no fee. Cancellation policy version, retained amount, refund amount, and cancellation timestamp are persisted.
- Hotel service start uses the reservation check-in date/time in India Standard Time. Charging uses the slot start timestamp. Post-start hotel cancellation does not release inventory for the current/past stay dates; future nights are released. Charging slots are not reopened after their start time.
- Mobile cancellation confirmations display the estimated refund and retained amount, and cancellation detail models show the recorded amounts. Server values remain authoritative if time passes between quote and confirmation.
- The additive cancellation schema migration is `supabase/migrations/202610200001_customer_cancellation_policy.sql`. It is safe to re-run when some columns already exist. No production database was modified here.
- Hotel partial refund completion is represented as `refund_partial`; only a completed refund equal to the full captured amount marks the payment and reservation fully refunded.
- Refund is still finance-reviewed and submitted through the configured Razorpay flow. Restaurant cancellation is outside this policy because restaurant order cancellation lifecycle is not implemented.

## P1 — Booking cancellation and refund gaps (verified in code)

### Charging bookings (previous behavior; locally updated)

- Previously, `POST /api/v1/bookings/{booking_id}/cancel` only permitted pending bookings. It now permits confirmed bookings with captured, webhook-verified payments and creates a partial customer refund request under the approved policy. Existing finance approval and refund webhook processing remain in control of money movement.

### Hotel reservations (previous behavior; locally updated)

- Room offers store `free_cancellation_hours`; reservations snapshot that value.
- Previously, a confirmed stay was limited by the vendor's free-cancellation cutoff and eligible cancellation requested a full refund. The new policy replaces that cutoff for customer cancellation quotes and requests a partial or full refund based on check-in time.
- Finance approval remains required before Razorpay submission. Zero-refund post-start cancellation is recorded without creating a zero-value provider refund; future room nights are released while current/past dates remain occupied.

### Restaurant orders

- The restaurant API exposes menu, create-order, and order-list routes, but no customer order-cancellation route was found in the inspected router.

### Remaining cancellation release checks

- Publish the policy and expected refund-review timing in the customer terms and before purchase. Existing vendor `free_cancellation_hours` is no longer the customer cancellation computation and should be relabelled/retired if vendors continue to see it.
- Apply the matching migration, deploy the API/mobile build, verify refund records appear in the finance console, and run staging cases at 49, 48, 24, 1, and 0 hours plus duplicate requests and failed/approved refunds. These tests were not run in this audit session.
- Keep Supabase PostgreSQL as the sole application database. The API's `DATABASE_URL` must use the Supabase transaction pooler for Vercel deployments.

## P1 — Payment and settlement readiness

- The API code requires `RAZORPAY_WEBHOOK_SECRET` in production mode, verifies signed webhook events, and supports refund-webhook reconciliation. The deployed environment's current mode and secret configuration were not independently inspected in this review; the `/ready` liveness result alone does not prove payment checkout readiness.
- Verify test-mode order creation, payment capture, signed webhooks, duplicate delivery, delayed capture, partial refunds, provider timeouts, and reconciliation against a staging account before live collection.
- Vendor payout pages currently describe calculated amounts as estimates; the API declares vendor settlement transfers unconfigured and the payout ledger unimplemented. Do not label any amount as paid or processed.

## P1 — Charger availability and directions

- The app has corridor estimates and partner charger listings, but the existing audit and repository contain no verified contracted CPO/charger feed. Availability and price must remain labelled as partner-provided/unverified until a provider integration supplies freshness, connector compatibility, and operational status.
- The directions screen requests device location and only then calls the public OSRM route endpoint. In the supplied screenshot, location is disabled, so the destination marker appears but a route is not drawn. Offer a clear permission path or a selectable origin/fallback; do not present the route preview as navigation guidance. Public OSRM/OSM endpoints are not a production SLA.
- Nearby alerts are foreground/in-app behavior; background push delivery and live charger triggers are not verified.

## P1 — Identity, vendor onboarding, and data integrity

- Prior user-reported production issues included admin 403, vendor profile 404/422/500, and vendors missing from admin lists despite Supabase Auth accounts. These reports are not re-tested against the live database here. Validate role assignment, vendor row creation, migration state, and owner-scoped access in staging for customer, vendor, and admin accounts.
- A green API readiness probe does not prove every feature migration/table or policy is present. Reconcile the production `DATABASE_URL` provider and migration inventory before deploying schema-dependent code.
- Earlier conversation messages exposed account/payment/cache credentials. Rotate any reusable passwords and provider secrets, store only in provider environment settings, and never commit local signing/env files.

## P2 — Enterprise operations and product quality

- No current load/concurrency evidence was found for booking locks, database-pool limits, refunds, and serverless bursts. Define target traffic and test overbooking, duplicate payment/webhook, retry, and refund races.
- Add actionable alerting and runbooks for API/database health, webhook/refund reconciliation, queue/notification failures, and stale charger data; document backup/restore drills, ownership, and incident escalation.
- The earlier audit reported portal sidebar/map stacking and clipped service forms. Those visual issues were not rechecked in a live browser in this review. Re-run responsive keyboard/accessibility review at mobile, tablet, and desktop widths.
- The release APK build was reported successful at 58.2 MB, but physical-device install/upgrade, account login, network handoff, payment, and crash behavior have not been verified here. Gradle settings were locally modified to reduce build memory pressure; inspect that diff before committing.
- Before broad launch, review privacy/consent, data retention/deletion, customer terms/refund disclosures, tax receipts, support SLAs, and partner operating agreements with the responsible business/legal owners.

## Release gates

1. Apply the matching cancellation migration, deploy API/mobile changes, publish the approved temporary terms, then validate quote boundaries, finance approval, and Razorpay refund-webhook reconciliation in staging.
2. Prove migration state and role-specific account journeys against staging.
3. Complete Razorpay test-mode order, webhook, cancellation, partial-refund, failure, and replay scenarios; keep payouts disabled until ledger and transfer reconciliation exist.
4. Obtain a CPO/provider feed before advertising live availability or background charger alerts.
5. Verify route UX with location granted/denied and fallback origins on physical devices.
6. Complete release APK install/upgrade and full backend/mobile/web validation, plus load, backup/restore, and incident drills.

## Current decision needed

No further policy decision is blocking this first implementation. Business/legal review is still needed before advertising the policy as final, and production use remains gated on migration, deployment, and staging reconciliation.
