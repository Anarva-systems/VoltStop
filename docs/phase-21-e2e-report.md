# Phase 21 E2E Report

Date: 2026-10-03. No external test identity, staging service, or financial data was used. The real booking-to-refund E2E flow could not be run because no staging environment was configured.

| Stage | Input | Expected result | Observed result | Status | Evidence / test reference |
|---|---|---|---|---|---|
| Customer login | Supabase staging test identity and phone OTP | Authenticated customer session | No Supabase URL/keys or service endpoint available; no login attempted | BLOCKED | Environment audit; local auth tests are mocked |
| Profile | Authenticated test customer and profile payload | Server persists owned profile | No live API/database available | BLOCKED | Local profile endpoint tests use fake DB |
| Route planning | Srikakulam → Vijayawada, EV profile, Maps/Routes key | Provider route, estimate and recommended pitstops | Fake route-provider test passed; no real route request | BLOCKED (E2E) | `test_api.py` route service tests |
| Pitstop discovery/service selection | Staging corridor vendors and services | Owned/available vendor details and selected service | Discovery test uses a fake vendor | BLOCKED (E2E) | Nearby/vendor unit test |
| Slot selection/Redis lock | Available staging slot, two concurrent customers | One short-lived lock, no double booking, expiry/release | Fake Redis lock tests pass in suite; Redis endpoint unavailable | BLOCKED (integration) | Booking lock tests; external Redis probe skipped |
| Booking creation | Valid user, slot lock, server-side price | Pending booking and provider order | Fake gateway/API tests exercise pending booking; no database or Razorpay order created | BLOCKED (E2E) | Booking API unit tests |
| Payment capture | Razorpay test order/payment | Provider capture linked to stored order and payment | No Razorpay test account or credentials; no capture attempted | BLOCKED | Razorpay probe skipped |
| Webhook confirmation/replay | Real signed provider webhook and replay | Valid event confirms once; invalid identity/amount/order is rejected without mutation | Phase 20 test suite passes with local SQL/API doubles; no provider delivery or Postgres state | BLOCKED (integration) | 13 repository tests + 4 API webhook tests passed locally |
| Vendor booking view/acceptance | Vendor owner test account and confirmed booking | Owner sees only own booking and makes allowed transition | Selected owner-scope tests use fake DB; no vendor login/database | BLOCKED (E2E) | Full backend unit suite |
| Booking completion/use | Confirmed booking and staging service activity | Valid lifecycle completion | No staging booking/service record | BLOCKED | No live flow run |
| Customer dispute | Owned eligible paid booking | Customer opens/reads only own dispute and sends message | Selected dispute authorization/idempotency tests use fake DB; no persisted case | BLOCKED (E2E) | Full backend unit suite |
| Vendor response/admin review | Owned dispute, vendor and permitted admin identities | Vendor responds; admin reviews with RBAC | Unit permission tests exist; no real role/session or dispute timeline | BLOCKED (E2E) | Full backend unit suite; admin auth is server-side in code |
| Refund request/approval | Eligible captured payment and allowed finance/admin actor | Server-derived full/partial amount, permitted approval, linked audit | Refund amount/idempotency tests use fake repository; no provider or DB action | BLOCKED (E2E) | Full backend unit suite |
| Razorpay refund/result webhook | Razorpay test refund and signed result | Refund updates once and parent payment state is consistent | No provider refund issued; no refund webhook received | BLOCKED | External Razorpay probe skipped |
| Financial diagnostics | Staging payment/booking/refund records | Read-only findings and explicit truncation status | Diagnostics were not run against data | BLOCKED | Source reviewed only |
| Audit trail | Persisted booking/payment/dispute/refund/admin events | Expected append-only event/audit rows | No staging DB; SQL triggers were not exercised | BLOCKED | Migrations and repository code inspected only |

## E2E conclusion

Local unit/API evidence is useful but does not establish any of the service integrations above. Full booking → payment → vendor → dispute → refund → webhook → audit E2E is **BLOCKED**, not passed or partially simulated as an integration result.
