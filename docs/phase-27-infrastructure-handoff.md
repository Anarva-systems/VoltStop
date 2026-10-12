# Phase 27 — Infrastructure Recovery, Staging Provisioning & Readiness Gate

Date: 2026-10-04
Operator: autonomous Phase 27 execution (primary senior engineer role)
Result: **BLOCKED** (local infrastructure fully provisioned and verified; external staging dependencies absent)
Phase 28 authorization: **NOT AUTHORIZED**

---

## 1. Phase Objective

Break the infrastructure bottleneck accumulated across Phases 19–26 by diagnosing, repairing, and
provisioning every piece of staging infrastructure that can be legitimately provisioned on this machine,
then run the full readiness gate. Produce truthful evidence for every gate, and either authorize
Phase 28 (full real-payment E2E) or declare BLOCKED with exact unblock requirements.

## 2. Previous Blockers (Phases 19–26)

All Phase 19–26 gates were BLOCKED for the same root cause chain: no Docker/Podman daemon, no
Supabase CLI, no psql, no redis-cli, no Flutter SDK, no Razorpay TEST credentials. The previous
Phase 27 attempt (2026-10-03, `docs/phase-27-readiness.json` of that date) ended BLOCKED with
0 staging gates passed and only offline code audits + local pytest (75 passed / 3 skipped).

New capability this attempt: Docker Desktop 29.8.0 and Compose were installed and the daemon
recovered. npm-based Supabase CLI 2.119.0 was available. This unlocked the repository-supported
local stack (`supabase start`, documented in `README.md`).

## 3. Repository Audit

| Component | Path | Stack |
| --- | --- | --- |
| Backend API | `apps/api` | FastAPI, asyncpg, redis.asyncio, httpx, Pydantic v2, Python 3.12.14 (venv at `.venv`) |
| Vendor + admin web | `apps/vendor-web` | Next.js 15.5.27, React 19, TypeScript 5.7, Tailwind 4, @supabase/supabase-js 2.117 |
| Mobile (driver) | `apps/mobile` | Flutter app (`pubspec.yaml`, `lib/`, `test/`) — SDK absent on machine |
| Database | `supabase/` | 5 SQL migrations, `seed.sql`, `verify.sql`, `config.toml` (project_id `voltstop`) |

Modules: auth, bookings, payments (+webhook), refunds, disputes, vendors, slots, pitstops,
profile, users, notifications, admin (RBAC + audit), finance. No background worker component
exists in the repository (no celery/arq/apscheduler/rq in dependencies; no worker entrypoint).

## 4. Environment Audit

| Tool | Version | Status |
| --- | --- | --- |
| Docker | 29.8.0 (build 88096ef) | available (daemon recovered by launching Docker Desktop) |
| Supabase CLI | 2.119.0 (npm) | available |
| Python | 3.12.14 (project venv) | available |
| Node | v24.21.0 | available |
| PostgreSQL (local stack) | 15.19 (supabase_db_voltstop container) | running |
| Redis (isolated container) | 7.4.11 (redis:7-alpine) | running |
| psql / redis-cli | via `docker exec` into project-owned containers | available |
| Flutter / Dart | — | **ABSENT** (`where flutter dart` finds nothing) |
| Git metadata | — | **ABSENT** (`fatal: not a git repository`) |

Host is multi-tenant: other projects' containers (qe360-postgres on 5432, qe360-redis on 6379)
were identified via netstat + `docker ps` and **never touched**. VoltStop uses 54321–54324
(Supabase), 127.0.0.1:6397 (VoltStop Redis), 8000 (API), 3000 (web).

## 5. Infrastructure Strategy

The repository's documented workflow (`README.md`) is the Supabase local stack: `supabase start`,
`supabase db reset`, verify via `supabase/verify.sql`. That is the only repository-supported
provisioning path and it was adopted for the local environment:

- PostgreSQL: Supabase local Postgres (container `supabase_db_voltstop`, port 54322), owned by
  this phase's `supabase start`, fully identified.
- Redis: dedicated isolated container `voltstop-phase27-redis` (label `voltstop.phase=27`),
  bound to 127.0.0.1:6397, `--requirepass` with a generated local secret, AOF off.
- API: uvicorn started with process-environment overrides; root `.env` untouched.
- No unknown localhost service was connected to. Every connected endpoint was proven to belong
  to a container this phase or the repository started.

Note on classification: the Supabase **local** stack is LOCAL verification, not cloud staging.
`apps/api/app/core/config.py` structurally forbids `ENVIRONMENT=staging` from using localhost
endpoints (requires HTTPS non-local Supabase, credentialed non-local Postgres, `rediss://`
TLS Redis with password, `rzp_test_` keys, HTTPS portal origin). Therefore the API can only be
legitimately started as `ENVIRONMENT=development` against local infrastructure; a real
`staging` deployment requires external resources that do not exist (see Blockers).

## 6. PostgreSQL — PASS (LOCAL)

- Container `supabase_db_voltstop`, PostgreSQL 15.19, port 54322.
- Extensions: PostGIS, pgcrypto, supabase_vault present (schema check).
- Connection from API verified through the app's asyncpg pool (health + vendor endpoints 200).

## 7. Redis — PASS (LOCAL); TLS BLOCKED (external)

- Container `voltstop-phase27-redis` (redis:7-alpine 7.4.11), 127.0.0.1:6397 only.
- Auth enforced: unauthenticated commands rejected with NOAUTH; password (generated local
  secret, stored `D:\voltstop\.redis-phase27.pass`, never printed) allows SET/GET/DEL.
- App-level smoke through `redis.asyncio`: acquire (SET NX EX) → verify → release (Lua
  compare-and-delete) → confirmed deleted; booking-lock flow 9/9 via live API (section 17).
- TLS (`rediss://`): not possible on a local container without cert provisioning; required
  only for `ENVIRONMENT=staging`, which is externally blocked anyway. Local `redis://` with
  password is the correct configuration for local development.

## 8. API — PASS (LOCAL)

Started with process-env overrides (root `.env` untouched):
`ENVIRONMENT=development`, `SUPABASE_URL=http://127.0.0.1:54321`,
`DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres`,
`REDIS_URL=redis://:<generated-local-secret>@127.0.0.1:6397/0`,
uvicorn on 127.0.0.1:8000. Verified:

- `GET /api/v1/health` → 200
- `GET /api/v1/vendors/nearby?lat=..&lng=..&radius_km=..` → 200 (PostGIS distance + seed data)
- `GET /api/v1/vendors/{id}/slots` → 200
- Logs clean; no secret values logged.

## 9. Worker — NOT APPLICABLE

The repository contains no background worker (no celery/arq/rq/apscheduler dependency, no
worker entrypoint). Nothing to start.

## 10. Web — PASS (LOCAL)

- `tsc --noEmit` → exit 0.
- `next build` → exit 0 (twice; second build with `NEXT_PUBLIC_SUPABASE_URL`,
  `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL` pointing at the local stack).
- `next start -p 3000`: `/login` → 307 → `/vendor/login` → 200; `/admin/login` → 200;
  Supabase configuration warning absent after env-baked rebuild (client env vars are inlined
  at build time — first run showed the warning with runtime-only env, rebuilt correctly).
- CORS preflight from portal origin `http://localhost:3000` → allowed; foreign origin
  `http://evil.example` → no CORS grant (verified against live API).

## 11. Supabase — PASS (LOCAL STACK); CLOUD STAGING BLOCKED

- `supabase start` brought up the full local stack (kong, auth/GoTrue, rest, storage,
  realtime, studio, inbucket/mailpit, edge runtime, analytics, vector, db).
- `supabase db reset` applies all 5 migrations deterministically + `seed.sql`, no errors.
- `supabase migration list --local` and `supabase/verify.sql` pass.
- GoTrue: signup with `GOTRUE_MAILER_AUTOCONFIRM=true` returns a flat response with top-level
  `access_token` (not nested `session`) — smoke script parsing fixed accordingly.
- Cloud Supabase project for real staging: does not exist (no credentials). BLOCKED.

## 12. Razorpay TEST — BLOCKED (credentials absent)

`.env` has empty `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` / `RAZORPAY_WEBHOOK_SECRET`;
`.env.integration.local` (referenced by integration tests) does not exist. No genuine
Razorpay TEST credentials exist on this machine. Per the rules: no fabricated credentials, no
production credentials, no faked payment verification. Effects:

- `POST /bookings` with a valid lock correctly returns 503 `PAYMENT_UNAVAILABLE` at the
  provider boundary (verified live — this is the intended fail-closed behavior).
- Positive-path payment/refund/webhook processing cannot be verified against the real
  provider; it is covered by unit tests only (code-verified, not real-verified).

## 13. Webhook — ROUTE PASS (LOCAL, FAIL-CLOSED); EXTERNAL REACHABILITY BLOCKED

- Route `POST /api/v1/payments/razorpay/webhook` exists and is reachable on the local API.
- Signature verification happens before any payload parsing.
- Live negative tests: unsigned request → 401 `INVALID_WEBHOOK_SIGNATURE`; forged
  `X-Razorpay-Signature` → 401 `INVALID_WEBHOOK_SIGNATURE`. Fail-closed confirmed.
- With no webhook secret configured, every webhook is rejected (correct).
- External reachability (Razorpay servers → public HTTPS endpoint): no public staging host
  exists. BLOCKED. Unit tests (12) cover signature acceptance/rejection logic locally.

## 14. Synthetic Fixtures — PASS

All created in the local isolated stack with synthetic data only (no real customer, vendor,
or financial data):

| Fixture | Identity |
| --- | --- |
| Customer A | `phase27-customer@voltstop.test` |
| Customer B | `phase27-customer-b@voltstop.test` (also granted SUPPORT_ADMIN for RBAC test) |
| Vendor A | `phase27-vendor@voltstop.test` + unverified profile "phase27 pitstop" |
| Vendor B | `phase27-vendor-b@voltstop.test` + unverified profile "phase27 pitstop b" |
| Admin | `phase27-admin@voltstop.test` (SUPER_ADMIN via `admin_users`) |

These users persist in the local Supabase volume and are reusable for Phase 28 local work.
Seed data (7 verified public vendors, slots, services) came from `supabase/seed.sql`.

## 15. Authentication — PASS (LOCAL)

Live smoke (`.phase27/auth_smoke.py`, 11/11):

- Customer register (GoTrue signup, autoconfirm) → session issued.
- Customer login (password grant) → access token.
- `GET /auth/me` with bearer → 200, id matches GoTrue user.
- `GET /profile` → 200 (row created by DB trigger), `PATCH /profile` → 200.
- Unauthenticated `/profile` → 401.
- Vendor register + `POST /vendor/profile` → 200 with `is_verified=false` (hidden from
  discovery until admin verification — correct).
- `GET /vendor/profile`, `GET /vendor/dashboard` → 200 (owner-scoped).
- Admin login + `GET /admin/me` → 200 role SUPER_ADMIN, 19 permissions.
- Logout: no server-side session store (JWT bearer tokens; GoTrue-managed). Token revocation
  is a GoTrue feature, not an API route — NOT APPLICABLE locally.

## 16. RLS — PASS (LOCAL)

Direct SQL baseline (`.phase27/rls_baseline.sql` against `supabase_db_voltstop`):

- All 17 public tables have RLS enabled.
- Customer A sees exactly 1 profile row (own); customer B's row invisible (0); payments 0,
  bookings 0, notifications 0.
- Customer A cannot update customer B's profile (UPDATE 0); INSERT/DELETE on profiles denied
  by revoked grants.
- Vendor A sees own unverified vendor row (1), vendor B's row (0), and no other unverified
  rows (1 total = own only). Vendor A cannot update vendor B's row (UPDATE 0).
- anon sees 7 public verified/active vendors, 0 non-public, 0 profiles, 0 bookings.
- `disputes`/`dispute_events`: RLS enabled with ZERO policies + SELECT/INSERT/UPDATE/DELETE
  revoked from anon/authenticated (service_role retains access) — intentional default-deny;
  access only via owner-scoped API queries.
- Privilege escalation attempt: JWT with `user_metadata.role=admin` → `is_platform_admin()`
  returns false, bookings visible 0. Admin claim must be in protected `app_metadata`.

## 17. Redis Booking Lock — PASS (LOCAL)

Live smoke (`.phase27/booking_smoke.py`, 9/9) against the running API + isolated Redis:

1. Acquire lock on seeded slot → 200, lock token, TTL 300s.
2. Same user second lock → 409 SLOT_LOCKED.
3. Different user lock → 409 SLOT_LOCKED (mutual exclusion across users).
4. Forged (schema-valid length) lock token → 409 SLOT_LOCK_EXPIRED.
5. Cross-user token (customer B using A's token) → 409 SLOT_LOCK_EXPIRED.
6. Valid token → flow proceeds to payment boundary → 503 PAYMENT_UNAVAILABLE
   (Razorpay TEST credentials absent — external blocker, not a code defect).
7. Lock correctly released by the `finally` block despite the 503 (re-acquire → 200).
8. Unknown slot → 404 SLOT_NOT_FOUND.
9. Unauthenticated lock → 401.

No `voltstop:*` keys remain in Redis after the run (verified).

## 18. Payment Security Audit — PASS (CODE + LIVE NEGATIVE)

`apps/api/app/core/database.py::process_payment_webhook`:

- Provider identity verified BEFORE duplicate/terminal handling: stored `razorpay_payment_id`
  must match (Phase 20 requirement), currency and amount (paise, via Decimal) must match the
  stored payment — any mismatch → 400 PAYMENT_WEBHOOK_REJECTED.
- Cross-booking pointer verified with row locks (`for update` on bookings then payments).
- Duplicate provider payment across different local payments → rejected.
- Terminal states (captured/refunded) ignore replays; failed-replay acknowledged without writes.
- Transitions: pending → captured/failed (+ booking confirmed/expired, slot re-released only
  when no pending/confirmed bookings remain below capacity); UniqueViolationError on
  `razorpay_payment_id` is the final race guard.
- Webhook signature: HMAC-SHA256, `hmac.compare_digest` constant-time, checked before payload
  parsing; live unsigned/forged → 401.

## 19. Refund Security Audit — PASS (CODE)

- `apps/api/app/finance/refunds.py::validate_refund_amount`: refund ≤ captured − already
  refunded; positive amounts only; 409s otherwise.
- `apps/api/app/admin/refund_service.py::RefundService`: the only service allowed to call
  Razorpay refunds; atomically claims an approved request (single-flight), and on ambiguous
  provider responses (timeout, HTTP 5xx, unparseable body) holds the refund in `processing`
  for reconciliation instead of retrying blindly; provider rejections (HTTP 4xx) mark failed.
- `process_refund_webhook`: refund identity bound by `razorpay_refund_id` + payment
  `razorpay_payment_id`; currency/amount verified; state map validated; dispute events and
  admin audit logs written; payment flips to `refunded` only when Σ completed refunds ≥
  captured amount.

## 20. Dispute Security Audit — PASS (CODE + RLS)

- Disputes/dispute_events fully default-deny at DB level (RLS on, no policies, grants
  revoked); owner-scoped API access only; creation is idempotent via idempotency key in
  dispute_events; events are append-only with immutability triggers; refund linkage and
  party/amount fields hardened by `202610020005_dispute_hardening.sql`.

## 21. Audit Logging — PASS (CODE)

Sensitive flows write `admin_audit_logs` (refund webhooks, admin decisions with before/after
state + request metadata). Admin tables RLS-enabled with default-deny.

## 22. Secret Hygiene — PASS

- No secret values printed in any output; Redis password kept in `.redis-phase27.pass`
  (generated local secret, distinct from external provider credentials).
- Root `.env` never modified; API started via process-environment overrides.
- Razorpay fields empty (truthfully absent, not fabricated). The Supabase local-stack keys
  used are machine-generated local values, safe for local development only.
- Production safety: staging validator refuses localhost/HTTP/insecure values, so the local
  environment can never accidentally satisfy staging or production settings.

## 23. Git — BLOCKED

`D:\voltstop` is not a git repository (`fatal: not a git repository`). No commit/branch/CI
verification possible. Restoring git history requires the repository remote/backup — external
dependency.

## 24. Flutter — BLOCKED

Flutter/Dart SDK absent from PATH (`where flutter dart` → not found). `apps/mobile` exists
(pubspec, lib, test) but cannot be built, analyzed, or tested. No results fabricated.

## 25. Backend Tests — PASS

`.venv/Scripts/python.exe -m pytest apps/api/tests` → **75 passed, 3 skipped** in 15.94s.
The 3 skipped are integration tests gated behind `RUN_INTEGRATION_TESTS` + real
`.env.integration.local` (Razorpay) — correctly skipped, matching previous phases.

## 26. Web Tests — PASS

- Type check `tsc --noEmit` → exit 0 (the package's `lint` script).
- Production build `next build` → exit 0.
- Runtime smoke: pages serve, Supabase env wired, redirects correct.
- No separate unit-test runner exists for vendor-web (no test script in package.json).

## 27. Configuration Tests — PASS

15 config tests in `apps/api/tests/test_config.py` all pass within the 75. They enforce the
staging/production hardening rules (localhost forbidden, `rediss://` required, Razorpay
prefixes, portal HTTPS). The validator itself was audited: it is the structural reason a
local stack can never impersonate staging — working as intended.

## 28. Warnings

1. Multi-tenant Docker host: other projects' containers run on this machine (ports 5432/6379).
   Any future automation must keep using VoltStop's dedicated ports (54321–54324, 6397, 8000, 3000).
2. Vendor-web client env vars are inlined at build time; a rebuild is required whenever
   `NEXT_PUBLIC_*` values change (cost an extra build cycle this phase).
3. Local GoTrue has `GOTRUE_MAILER_AUTOCONFIRM=true` (local-only convenience; mailpit at
   54324 had 0 messages, as expected). Production must not autoconfirm.
4. The 3 skipped integration tests are the only automated coverage of real provider calls;
   they remain unexecuted until real TEST credentials exist.
5. `phase27-smoke-tokens.json` (bearer tokens) was a temporary artifact and is deleted;
   fixture users persist in the local DB for reuse.

## 29. Failures (encountered and resolved during this phase)

| # | Failure | Root cause | Resolution |
| --- | --- | --- | --- |
| 1 | Docker daemon unreachable | Docker Desktop not running | Launched Docker Desktop, waited for daemon (29.8.0) |
| 2 | `supabase start` exceeded 2-min command timeout | large image pulls on first run | moved to background task; completed exit 0 |
| 3 | psql errors on `tgrelid::regclass::regnamespace` | cast unsupported on PG15 | rewrote using `::regclass::text` / information_schema |
| 4 | Mailpit API v2 404 | wrong endpoint version | used v1 `/api/v1/messages` |
| 5 | auth smoke: "signup returned no session" | GoTrue local signup returns flat response (top-level `access_token`), not nested `session` | fixed parser; made signup idempotent (falls back to password login when user exists, since the failed first run had already created the user) |
| 6 | booking smoke: forged token got 422 not 409 | forged value violated schema `min_length=24` before reaching comparison logic | used a schema-valid-length forged token → 409 SLOT_LOCK_EXPIRED |
| 7 | web portal showed Supabase config warning | NEXT_PUBLIC vars inlined at build; passed only at runtime | rebuilt with env vars, warning gone |

No repository source code was modified. All fixes were to phase-local smoke tooling,
tooling invocation, or environment state.

## 30. Blockers

1. **Razorpay TEST credentials** (key id/secret with `rzp_test_` prefix + webhook secret) do
   not exist on this machine. Blocks: real test payment, real refund, positive-path webhook,
   payment replay verification, and the 3 integration tests. Required: a human with a Razorpay
   dashboard account creating TEST-mode credentials and a TEST webhook endpoint, then placing
   them in `.env.integration.local` (never committed).
2. **Public staging host** (HTTPS endpoint reachable by Razorpay + cloud Supabase project +
   TLS Redis) does not exist. `ENVIRONMENT=staging` is structurally impossible to satisfy
   locally (by design). Required: provision a cloud Supabase project, a managed Redis with
   TLS, and a public HTTPS deployment target, plus the `.env.staging` values.
3. **Flutter SDK** absent — driver-app build/test/analysis blocked. Required: install Flutter
   SDK matching `apps/mobile/pubspec.yaml`.
4. **Git repository metadata** absent — version-control and CI verification blocked.
   Required: restore/clone from the project's remote.

## 31. Evidence

- Live smoke scripts (retained): `.phase27/auth_smoke.py` (11/11), `.phase27/booking_smoke.py`
  (9/9), `.phase27/admin_smoke.py --verify` (3/3), `.phase27/rls_baseline.sql` (all checks).
- Live HTTP checks documented above (health, vendors, slots, webhook 401s, admin 401/403/200s,
  CORS preflight, web pages).
- Test runs: pytest 75 passed / 3 skipped; tsc exit 0; next build exit 0 (x2).
- `supabase db reset` + `supabase/verify.sql` + schema inspection outputs.
- Machine-readable results: `docs/phase-27-readiness.json`.

## 32. Final Readiness Decision — BLOCKED

Local isolated infrastructure is fully provisioned and verified end-to-end (database,
migrations, schema, RLS, auth, RBAC, Redis locks, API, web, fail-closed webhook). The
staging-critical external dependencies (Razorpay TEST credentials, public staging hosting,
cloud Supabase) do not exist and cannot be fabricated. Phase 28's mandatory scope (REAL
BOOKING, RAZORPAY TEST PAYMENT, REAL WEBHOOK, PAYMENT REPLAY, refunds, financial consistency
with a real provider) cannot be executed truthfully. A truthful BLOCKED is the correct result.

## 33. Phase 28 Authorization — NOT AUTHORIZED

Phase 28 (real payment E2E) must not run until Blockers 1 and 2 are resolved by their owners.
When they are: re-run `supabase start` (or point at the cloud project), start API with
staging env, re-run `.phase27/*` smokes, execute the 3 integration tests, then authorize.

## Readiness Matrix (STEP 31)

| Area | Requirement | Result | Evidence |
| --- | --- | --- | --- |
| Repository | audited | PASS | section 3 |
| Toolchain | available | PASS | section 4 (Flutter absent, separately blocked) |
| PostgreSQL | trusted | PASS | supabase_db_voltstop, project-owned container |
| PostgreSQL | isolated | PASS | port 54322, VoltStop-dedicated |
| PostgreSQL | connected | PASS | health/vendors 200 via asyncpg |
| PostgreSQL | migrations | PASS | 5/5 via `supabase db reset` |
| PostgreSQL | schema | PASS | verify.sql + 17 tables/constraints/triggers |
| Redis | trusted | PASS | voltstop-phase27-redis, labeled, 127.0.0.1:6397 |
| Redis | TLS | BLOCKED | local container; `rediss://` needs external staging |
| Redis | auth | PASS | NOAUTH without password, generated local secret |
| Redis | connected | PASS | app redis.asyncio smoke + live lock flow |
| Redis | smoke | PASS | acquire/verify/release + 9/9 API lock tests |
| API | staging config | BLOCKED | validator forbids localhost staging (by design) |
| API | startup | PASS | uvicorn local, process-env overrides |
| API | health | PASS | 200 |
| Worker | startup | NOT APPLICABLE | no worker in repository |
| Web | staging config | PASS (LOCAL) | env-baked build to local stack |
| Web | build | PASS | tsc 0 + next build 0 |
| Auth | customer | PASS | 11/11 smoke |
| Auth | vendor | PASS | register/profile/dashboard smoke |
| Auth | admin | PASS | SUPER_ADMIN 200/19 perms; 403 non-admin |
| RLS | customer isolation | PASS | SQL baseline |
| RLS | vendor isolation | PASS | SQL baseline |
| Booking | infrastructure baseline | PASS | slot found, availability 200, lock reachable |
| Redis Lock | baseline | PASS | 9/9 |
| Razorpay | TEST config | BLOCKED | credentials absent |
| Webhook | route | PASS | POST /payments/razorpay/webhook |
| Webhook | reachability | BLOCKED | no public HTTPS host for provider callbacks |
| Webhook | signature verification | PASS | live 401 unsigned/forged + 12 unit tests |
| Payment | security code audit | PASS | section 18 |
| Refund | security audit | PASS | section 19 |
| Dispute | security audit | PASS | section 20 |
| Audit | implementation audit | PASS | section 21 |
| Secrets | hygiene | PASS | section 22 |
| Git | integrity | BLOCKED | not a git repository |
| Flutter | availability | BLOCKED | SDK absent |
| Backend | regression | PASS | 75 passed / 3 skipped |
| Web | regression | PASS | tsc + build + runtime smoke |
| Config | safety | PASS | 15 config tests + validator audit |
