# Phase 23 Environment Security Audit

Audit date: 2026-10-03. Secret values are intentionally omitted. The root `.env` was not read.

## Git status and tracked secrets

Git is installed, but `D:\voltstop` and its parent do not contain Git metadata. `git status` and `git ls-files` both fail with “not a git repository.” Whether existing files are tracked or staged therefore remains **BLOCKED / UNKNOWN**. No repository was initialized because that would create a new empty history and would not verify the original tracked/index state.

`.gitignore` now ignores `.env` and `.env.*`, with explicit exceptions for `.env.example` and `.env.integration.example`. This behavior was verified in a temporary disposable Git repository:

- Ignored: `.env`, `.env.local`, `.env.production`, `.env.integration.local`.
- Not ignored: `.env.example`, `.env.integration.example`.

This verifies the ignore rules but does not replace actual `git status`/`git ls-files` evidence for the project checkout.

## Secret exposure scan

A bounded source, docs, test, and built-web scan excluded the root `.env`, local environment files, dependency caches, and `.venv`. Candidate matches were limited to blank values in `.env.example`, obvious replacement placeholders in `.env.integration.example`, and synthetic values in backend tests. No live Razorpay key pattern, private-key header, or frontend service-role variable was found. The built web bundle had no candidate credential matches. Because there is no Git index, tracked-history exposure remains unverified; no secret value was printed.

## Production/staging settings

Before this phase, the API settings defaulted to `development`, empty database/provider settings, and local unauthenticated Redis without validating deployed environments. The API also had no explicit Razorpay mode setting. A fail-closed startup validator was added:

- Only `development`, `staging`, and `production` are accepted.
- Staging/production require Supabase HTTPS URL and anon key, explicit remote PostgreSQL identity, authenticated TLS Redis, explicit secure portal origin, Razorpay credentials, webhook secret, and explicit provider mode.
- Staging requires `RAZORPAY_MODE=test` and an `rzp_test_` key; production requires `RAZORPAY_MODE=live` and an `rzp_live_` key.
- Validation errors hide input values so credentials are not included in configuration failure text.
- Development retains local defaults for local development.

The API does not mint access JWTs or refresh tokens. It sends bearer tokens to Supabase Auth `/auth/v1/user` and relies on Supabase Auth/SDK for token and refresh handling. Therefore no local JWT signing or refresh secret is applicable; Supabase project signing/refresh configuration was not accessible to inspect.

The API does not use a Supabase service-role key: source uses the anon key for Auth validation and a configured PostgreSQL connection for data. The unused service-role setting was removed from API config and templates to avoid asking operators to provision an unnecessary privileged secret.

## CORS

The API uses one configured `VENDOR_PORTAL_ORIGIN` and `allow_credentials=False`. The new staging/production validator requires a specific HTTPS origin and rejects localhost, wildcard, credentials, path, query, and fragment. These conditions have unit coverage; no hosted CORS preflight was run.

## Database, Redis, Supabase, and Razorpay

No staging configuration values were supplied. `.env.integration.local` is absent. The environment template contains placeholders only. The root `.env` was not read. PostgreSQL/Redis connectivity and isolation remain unverified. No Supabase or Razorpay project was inspected.

## Frontend environment

The vendor web source uses `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, and `NEXT_PUBLIC_SUPABASE_ANON_KEY`; no service-role or provider secret is referenced by the web source. The integration template has an HTTPS staging API placeholder, but no runtime staging values were set. The local production build used its localhost API fallback, so it is not a staging-configured web artifact.

## Verification

- Config guard tests: **15 passed**.
- Full backend: **75 passed, 3 skipped, 0 failed**.
- Python compile: passed.
- Gitignore rules: passed in disposable temporary Git repo.
- Actual Git status/index: **BLOCKED** because checkout metadata is absent.
- Production deployment config, hosted Supabase auth settings, and provider config: **BLOCKED**.

