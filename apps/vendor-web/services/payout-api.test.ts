import assert from "node:assert/strict";
import { test } from "node:test";
import { apiGet, apiPost } from "./api.ts";
import { adminPost } from "./admin-api.ts";

process.env.NEXT_PUBLIC_API_URL = "https://api.voltstop.test/api/v1";

type Call = { url: string; method: string; headers: Headers; body?: string };

function stubFetch(response: { status: number; body: unknown }) {
  const calls: Call[] = [];
  const previous = globalThis.fetch;
  globalThis.fetch = (async (input: string | URL | Request, init: RequestInit = {}) => {
    calls.push({
      url: String(input),
      method: init.method ?? "GET",
      headers: new Headers(init.headers),
      ...(typeof init.body === "string" ? { body: init.body } : {}),
    });
    return new Response(JSON.stringify(response.body), {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;
  return { calls, restore: () => { globalThis.fetch = previous; } };
}

test("vendor payout endpoints are addressed under the vendor prefix", async () => {
  const fetchStub = stubFetch({ status: 200, body: { success: true, data: { state: "routing_enabled" } } });
  try {
    assert.deepEqual(await apiGet("/payout-status", "vendor-token"), { state: "routing_enabled" });
    await apiGet("/payout-transfers?limit=25", "vendor-token");
    assert.deepEqual(fetchStub.calls.map((call) => call.url), [
      "https://api.voltstop.test/api/v1/vendor/payout-status",
      "https://api.voltstop.test/api/v1/vendor/payout-transfers?limit=25",
    ]);
    assert.equal(fetchStub.calls[0]?.headers.get("authorization"), "Bearer vendor-token");
    assert.equal(fetchStub.calls[0]?.headers.get("accept"), "application/json");
  } finally { fetchStub.restore(); }
});

test("vendor KYC submission posts the masked payload", async () => {
  const fetchStub = stubFetch({ status: 200, body: { success: true, data: { kyc_status: "submitted" } } });
  try {
    const payload = { kyc_pan_masked: "ABCDE****F", bank_account_masked: "*****1234", kyc_gstin: null, kyc_reference: null };
    assert.deepEqual(await apiPost("/kyc", "vendor-token", payload), { kyc_status: "submitted" });
    const call = fetchStub.calls[0];
    assert.equal(call?.url, "https://api.voltstop.test/api/v1/vendor/kyc");
    assert.equal(call?.method, "POST");
    assert.equal(call?.headers.get("content-type"), "application/json");
    assert.equal(call?.body, JSON.stringify(payload));
  } finally { fetchStub.restore(); }
});

test("a verified vendor cannot resubmit and the portal keeps the error code", async () => {
  const fetchStub = stubFetch({
    status: 409,
    body: { success: false, error: { code: "KYC_ALREADY_VERIFIED", message: "Payout details are already verified.", details: [] } },
  });
  try {
    await assert.rejects(
      () => apiPost("/kyc", "vendor-token", { kyc_pan_masked: "ABCDE****F", bank_account_masked: "*****1234" }),
      (reason: unknown) => {
        const error = reason as Error & { status?: number; code?: string };
        assert.equal(error.status, 409);
        assert.equal(error.code, "KYC_ALREADY_VERIFIED");
        assert.match(error.message, /already verified/);
        return true;
      },
    );
  } finally { fetchStub.restore(); }
});

test("admin payout routing is addressed under the admin prefix", async () => {
  const fetchStub = stubFetch({ status: 200, body: { success: true, data: { payouts_enabled: true } } });
  try {
    const payload = { payouts_enabled: true, razorpay_linked_account_id: "acc_1a2b3c4d", commission_rate_bps_override: 400, reason: "Compliance review cleared" };
    assert.deepEqual(await adminPost("/vendors/vendor-1/payout-routing", "admin-token", payload), { payouts_enabled: true });
    const call = fetchStub.calls[0];
    assert.equal(call?.url, "https://api.voltstop.test/api/v1/admin/vendors/vendor-1/payout-routing");
    assert.equal(call?.method, "POST");
    assert.equal(call?.headers.get("authorization"), "Bearer admin-token");
    assert.equal(call?.body, JSON.stringify(payload));
  } finally { fetchStub.restore(); }
});
