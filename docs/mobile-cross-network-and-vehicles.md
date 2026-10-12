# Mobile connectivity, vehicles, and route departure

## Cross-network login

Supabase OTP and the VoltStop API are separate network services. The API URL is supplied at build time through `API_BASE_URL`; the development default `http://10.0.2.2:8000/api/v1` is for the Android emulator only. It is not a routable AP Fiber/mobile-data endpoint. The repository has no verified public HTTPS API deployment, DNS name, or TLS certificate, so an APK cannot yet be configured or acceptance-tested across external networks.

Deploy the existing FastAPI service to an HTTPS application host before building a production APK. Configure the service with the existing production environment guard, a dedicated PostgreSQL/Neon connection, authenticated TLS Redis, Supabase URL/publishable token validation settings, vendor portal origin, Razorpay keys and webhook secret. Keep secrets in the host's secret store. Verify `/api/v1/health`, HTTPS certificate chain, Supabase bearer-token verification, CORS for the vendor site, and protected `/api/v1/profile` and `/api/v1/vendors/nearby` requests from a device on AP Fiber and a second network. The health endpoint alone does not prove authenticated access.

Build a local emulator debug APK from the repository root with:

```powershell
cd D:\voltstop\apps\mobile
flutter build apk --debug --dart-define=APP_ENV=development --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
```

For an external-network production build, use only the verified HTTPS API origin:

```powershell
flutter build apk --release --dart-define=APP_ENV=production --dart-define=API_BASE_URL=https://<verified-api-host>/api/v1
```

The application displays a configuration error if `APP_ENV` is `staging` or `production` and the API URL is not HTTPS with a DNS host. Never ship the emulator or LAN URL as a production value.

## Vehicle migration and API

Apply `apps/api/migrations/neon/006_driver_vehicles_and_route_departure.sql` to the API's Neon schema, or `supabase/migrations/202610120001_driver_vehicles_and_route_departure.sql` to a Supabase-hosted schema. Do not apply both to the same database. The additive migration retains the old profile columns, copies complete legacy vehicle records into an owner-scoped vehicle table, adds a partial unique index for one default vehicle per customer, and adds route departure storage. Supabase RLS policies restrict direct table access by `auth.uid()`. Vehicle writes through FastAPI derive ownership from the verified token, serialize default changes per profile row, and require an idempotency key on creation.

API routes: `GET /api/v1/vehicles`, `POST /api/v1/vehicles`, `GET /api/v1/vehicles/{id}`, `PATCH /api/v1/vehicles/{id}`, `POST /api/v1/vehicles/{id}/default`, and `DELETE /api/v1/vehicles/{id}`. The server validates battery, efficiency, charge, connector names, ownership, and the default-vehicle transition. Route planning accepts an optional timezone-aware `departure_at`; route estimates do not reserve a charging slot. Charging reservations continue to use the existing dated slot availability and server-side capacity lock. Hotel check-in/check-out and guest/room count controls already exist. Food ordering is pickup-only; table bookings and scheduled pickup are not implemented by the current backend and are not presented as supported.
