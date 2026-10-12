# Development

See the repository README for exact startup commands for API, Docker/Redis,
local Supabase, Flutter, and vendor web.

- API: Python 3.12+, FastAPI/Uvicorn; run tests with
  `python -m pytest apps/api/tests` from repository root.
- Vendor web: Node 20.9+, npm; run `npm install`, then `npm run dev` from
  `apps/vendor-web`; strict TypeScript is enabled.
- Mobile: Flutter stable with Dart 3.4+; `flutter pub get`, `flutter run`.
- Supabase: install Supabase CLI, then `supabase start` and
  `supabase db reset` from repository root.
- Redis and API: `docker compose up --build`.

Copy `.env.example` to `.env`; do not commit `.env`. External maps/payment
credentials are optional until the corresponding integrations are developed.
Local Supabase credentials are available through `supabase status`.
