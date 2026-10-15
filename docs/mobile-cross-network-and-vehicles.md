# Mobile connectivity, vehicles, and route departure

## Cross-network login

Supabase OTP and the VoltStop API are separate network services. The API URL is supplied at build time through `API_BASE_URL`. Emulator loopback (`10.0.2.2`) and laptop LAN IPs only work on networks that can route to the development machine; they do not work over ordinary 4G/5G mobile data. This workspace currently has no verified public HTTPS API deployment, DNS name, or TLS certificate, so cross-network sign-in cannot be completed until the FastAPI service is deployed again.

The app now probes `/api/v1/ready` before it requests, resends, or verifies an OTP. If the API or a required backend dependency is down, it reports that no code was requested/used, so a user is not left at the profile screen after spending a code. This is a guard against the recurring failure path, not a substitute for a reachable API deployment.

Builds should use `apps/mobile/build_apk.ps1`. It requires an explicit API URL, checks the exact API's `/health` and `/ready` responses before compiling, and refuses to produce an artifact when the backend is missing or not ready. For an Android emulator with the local API running:

```powershell
cd D:\voltstop-1\production-work\apps\mobile
./build_apk.ps1 -ApiBaseUrl http://10.0.2.2:8001/api/v1 -BuildType debug -AppEnvironment development
```

For a phone on the same Wi-Fi as the laptop, use the laptop's current LAN IP only after the phone can open the API's `/api/v1/health` URL in its browser. This is a temporary development setup and depends on the laptop, network routing, and firewall staying available.

For 4G/5G and production, deploy FastAPI to a public HTTPS host first. Then build with that verified host and explicit Supabase project settings:

```powershell
./build_apk.ps1 -ApiBaseUrl https://<verified-api-host>/api/v1 -BuildType release -AppEnvironment production -SupabaseUrl https://<project>.supabase.co -SupabasePublishableKey <publishable-key>
```

The app now displays a configuration error when any build omits `API_BASE_URL`; it no longer silently uses an emulator-only default. The APK build script also checks the backend before building, so the deleted Vercel URL will fail preflight instead of being embedded into another APK.

## Vehicle migration and API

Apply `apps/api/migrations/neon/006_driver_vehicles_and_route_departure.sql` to the API's Neon schema, or `supabase/migrations/202610120001_driver_vehicles_and_route_departure.sql` to a Supabase-hosted schema. Do not apply both to the same database. The additive migration retains the old profile columns, copies complete legacy vehicle records into an owner-scoped vehicle table, adds a partial unique index for one default vehicle per customer, and adds route departure storage. Supabase RLS policies restrict direct table access by `auth.uid()`. Vehicle writes through FastAPI derive ownership from the verified token, serialize default changes per profile row, and require an idempotency key on creation.

API routes: `GET /api/v1/vehicles`, `POST /api/v1/vehicles`, `GET /api/v1/vehicles/{id}`, `PATCH /api/v1/vehicles/{id}`, `POST /api/v1/vehicles/{id}/default`, and `DELETE /api/v1/vehicles/{id}`. The server validates battery, efficiency, charge, connector names, ownership, and the default-vehicle transition. Route planning accepts an optional timezone-aware `departure_at`; route estimates do not reserve a charging slot. Charging reservations continue to use the existing dated slot availability and server-side capacity lock. Hotel check-in/check-out and guest/room count controls already exist. Food ordering is pickup-only; table bookings and scheduled pickup are not implemented by the current backend and are not presented as supported.
