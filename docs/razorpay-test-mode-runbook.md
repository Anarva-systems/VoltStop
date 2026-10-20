# Razorpay Test Mode on a phone

## API-only credentials

Use Razorpay **Test Mode** credentials in the API's ignored `.env`:

```dotenv
ENVIRONMENT=development
RAZORPAY_MODE=test
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=<Test Mode secret from Razorpay>
RAZORPAY_WEBHOOK_SECRET=<optional for a LAN-only checkout test; required for webhook delivery>
```

Keep `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET` on the API server only.
Do not put either value in Flutter `--dart-define`, the web app, or the APK. Do
not paste the secret into chat. After changing the API `.env`, restart the API.
The server refuses to create or verify orders if its mode and key prefix do not
match.

## Connect the phone to the local API

Run the API bound to `0.0.0.0` and build a debug APK with:

```powershell
flutter build apk --debug `
  --dart-define=APP_ENV=development `
  --dart-define=API_BASE_URL=http://<laptop-LAN-IP>:8001/api/v1
```

The local vendor web app uses the same port through `apps/vendor-web/.env.local`.
Keep that URL and the phone build's `API_BASE_URL` in sync.

Install that APK with the phone and laptop on the same Wi-Fi or the same phone
hotspot, and allow inbound access to the API port on the laptop. A phone using
its own 5G connection and a laptop on a separate network cannot reach the
laptop's private IP, even when both carriers are 5G. Use a public HTTPS API
deployment for separate networks.

On Windows, the firewall rule must match the API port (`8001`) and the current
local subnet. Run this in Administrator PowerShell if the phone cannot connect:

```powershell
New-NetFirewallRule -DisplayName "VoltStop API LAN 8001" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8001 -Profile Public -RemoteAddress LocalSubnet
```

An older rule for port `8000` or a different subnet does not permit this build.

## Checkout and verification

Sign in on the phone, choose an existing available charging slot, hotel room, or
restaurant item, then complete Razorpay's mock checkout with the provider's
Test Mode instrument. The app submits the checkout's order ID, payment ID, and
signature to `POST /api/v1/payments/razorpay/verify`. VoltStop verifies the
signature, confirms the signed-in user owns the order, reads the payment from
Razorpay, and updates the order only when the provider status is `captured`.
The webhook endpoint remains available for asynchronous confirmation.

Check that the app shows server-confirmed success and that the matching test
payment is `captured` in Razorpay Dashboard → Transactions → Payments. Also try
a cancelled/failed mock transaction and confirm it is not shown as paid.
Razorpay Test Mode simulates the payment and does not deduct real money.

Automated tests use clearly synthetic order/payment identifiers and a mocked
Razorpay response. No dummy rows were written to the configured Supabase database;
use a separate test database before inserting manual sample vendors, slots,
hotel inventory, or restaurant items.
