# Phase 29 — Staging Readiness Gate

**Date:** 2026-10-20
**Status:** CODE CHECKS PASS; EXTERNAL STAGING E2E BLOCKED
**Production readiness:** NOT ESTABLISHED

## Completed

- API configuration now rejects external PostgreSQL hosts that are not Supabase, including during development. Local Supabase hosts remain allowed; production and staging continue to reject local database hosts.
- Removed the unused Neon-specific root config and npm scaffolding; the API and web projects use their own manifests and Supabase configuration.
- Added a read-only PowerShell staging probe for `/health` and `/ready`. It requires HTTPS, refuses the known production API hostname, and can require Razorpay checkout and webhook readiness explicitly.
- Added a configuration regression test for rejecting an old external PostgreSQL host.
- Added boundary coverage for the current cancellation schedule: 48 hours or more returns 100%; 24–48 hours returns 90%; under 24 hours returns 50%; at/after service start returns 0%. Gateway fees are not deducted by this policy.
- Focused backend results: configuration and policy tests **29 passed**; payment checkout verification tests **7 passed**; Python syntax parsing and `git diff --check` passed.

## Current blocker

The local root `.env` still points `DATABASE_URL` at the legacy Neon host. This is now rejected by API configuration so local development cannot silently use that database. A staging template exists as `.env.integration.example`, but no populated `.env.integration.local` is available in the workspace. A live checkout was not attempted, and no dummy rows or payments were written.

The wider backend test run and webhook-security test did not complete in this environment; they were interrupted after hanging. They are not counted as passing.

## Required staging setup

1. Use a dedicated Supabase staging project with the required migrations and test data. Do not exercise cancellation/payment flows against production records.
2. Configure the staging API environment with `ENVIRONMENT=staging`, `RAZORPAY_MODE=test`, the staging Supabase URL/public key, and that project's PostgreSQL transaction-pooler `DATABASE_URL`.
3. Add the Razorpay TEST key ID and matching key secret to the API environment only. Never place the secret in the website, Flutter defines, APK, or Git.
4. To test webhook delivery, configure a Razorpay webhook to the staging HTTPS endpoint and set its matching `RAZORPAY_WEBHOOK_SECRET` on the API. Without that secret, test the signed checkout callback path only; webhook reconciliation remains unverified.
5. Verify staging `/api/v1/health` and `/api/v1/ready`, then test success, failed/cancelled payment, booking cancellation at each policy boundary, and refund reconciliation. Confirm the provider dashboard and database state agree before promoting any changes.

Run the non-mutating API probe from the repository root after step 2:

```powershell
.\apps\api\scripts\check_staging_readiness.ps1 -ApiBaseUrl "https://<staging-api-host>/api/v1"
```

Add `-RequirePaymentCheckout` after configuring the Razorpay test key and secret; add `-RequireWebhook` only after configuring a test webhook endpoint and secret.

Do not delete the old Neon project until its data has been reconciled and a verified Supabase backup and rollback plan exist. A successful health check alone does not establish that the correct database or every migration is active.
