import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  commissionRateLabel,
  formatRupees,
  kycValidationError,
  maskAccountId,
  payoutRoutingCopy,
  payoutRoutingPill,
  payoutRoutingValidationError,
  transferStatusLabel,
} from "./payout-view.ts";

test("routes a live vendor to the confirmed routing state", () => {
  assert.equal(payoutRoutingPill({ state: "routing_enabled" }), "captured");
  assert.match(payoutRoutingCopy({ state: "routing_enabled" }).detail, /split to your Razorpay account/);
});

test("tells the vendor which verification step is still missing", () => {
  assert.equal(payoutRoutingPill({ state: "kyc_required" }), "pending");
  assert.match(payoutRoutingCopy({ state: "kyc_required" }).label, /KYC/);
  assert.equal(payoutRoutingPill({ state: "account_required" }), "pending");
  assert.equal(payoutRoutingPill({ state: "disabled" }), "closed");
  assert.equal(payoutRoutingPill({ state: "rate_invalid" }), "failed");
});

test("never promises money moved when the platform gate is off", () => {
  assert.equal(payoutRoutingPill({ state: "ready_disabled" }), "limited");
  assert.match(payoutRoutingCopy({ state: "ready_disabled" }).detail, /not switched on/);
});

test("falls back to estimates-only copy for an unknown state", () => {
  assert.equal(payoutRoutingPill({ state: "something_new" }), "estimate_only");
  assert.equal(payoutRoutingCopy(null).label, "Estimates only");
});

test("commission label distinguishes the negotiated override from platform policy", () => {
  assert.equal(
    commissionRateLabel({ commission_rate_bps: 400, commission_rate_source: "vendor_override" }),
    "4% commission · agreed rate for your business",
  );
  assert.equal(
    commissionRateLabel({ commission_rate_bps: 500, commission_rate_source: "platform_policy" }),
    "5% commission · standard platform rate",
  );
  assert.equal(
    commissionRateLabel({ commission_rate_bps: null, commission_rate_source: null }),
    "Commission rate not recorded",
  );
});

test("linked account ids stay masked and absent accounts read honestly", () => {
  assert.equal(maskAccountId("acc_1a2b3c4d"), "acc_1a••3c4d");
  assert.equal(maskAccountId("acc_short"), "acc_••••");
  assert.equal(maskAccountId(null), "Not linked yet");
});

test("KYC form refuses raw documents the database would reject anyway", () => {
  assert.match(
    kycValidationError({ kyc_pan_masked: "ABCDE1234F", bank_account_masked: "*****1234" }) ?? "",
    /PAN/,
  );
  assert.match(
    kycValidationError({ kyc_pan_masked: "ABCDE****F", bank_account_masked: "50100123456789" }) ?? "",
    /masked bank account/,
  );
  assert.match(
    kycValidationError({ kyc_pan_masked: "ABCDE****F", bank_account_masked: "*****1234", kyc_gstin: "123" }) ?? "",
    /GSTIN/,
  );
  assert.equal(
    kycValidationError({ kyc_pan_masked: "ABCDE****F", bank_account_masked: "*****1234", kyc_gstin: "29ABCDE1234F1Z5" }),
    null,
  );
});

test("planned transfers are not labelled as money sent", () => {
  assert.equal(transferStatusLabel({ status: "planned" }), "planned_not_sent");
  assert.equal(transferStatusLabel({ status: "settled" }), "settled");
});

test("payout amounts keep paise instead of rounding to whole rupees", () => {
  assert.equal(formatRupees("672.5"), "₹672.50");
  assert.equal(formatRupees(1234.56), "₹1,234.56");
  assert.equal(formatRupees(null), "₹0.00");
});

test("the admin routing form refuses a commission below the retention floor", () => {
  const base = { linked_account_id: "acc_1a2b3c4d", commission_rate_bps: "", reason: "Provider account checked against the KYC record", payouts_enabled: true, account_on_file: true };
  assert.equal(payoutRoutingValidationError(base), null);
  assert.match(payoutRoutingValidationError({ ...base, commission_rate_bps: "200" }) ?? "", /300 and 5000 bps/);
  assert.match(payoutRoutingValidationError({ ...base, commission_rate_bps: "5100" }) ?? "", /300 and 5000 bps/);
  assert.match(payoutRoutingValidationError({ ...base, commission_rate_bps: "450.5" }) ?? "", /whole number/);
  assert.equal(
    payoutRoutingValidationError({ ...base, commission_rate_bps: "300" }),
    null,
    "the floor itself is allowed, only thinner rates stop routing",
  );
});

test("the admin routing form refuses bad accounts, blank reasons and routing without an account", () => {
  const base = { linked_account_id: "acc_1a2b3c4d", commission_rate_bps: "", reason: "Provider account checked against the KYC record", payouts_enabled: true, account_on_file: true };
  assert.match(payoutRoutingValidationError({ ...base, linked_account_id: "trf_1a2b3c4d" }) ?? "", /acc_/);
  assert.match(payoutRoutingValidationError({ ...base, reason: "ok" }) ?? "", /8 characters/);
  assert.match(payoutRoutingValidationError({ ...base, payouts_enabled: true, linked_account_id: "", account_on_file: false }) ?? "", /linked account on file/);
  assert.equal(
    payoutRoutingValidationError({ ...base, payouts_enabled: false, linked_account_id: "", account_on_file: false }),
    null,
    "switching routing off must stay saveable even with no account on record",
  );
});

test("every payout state the portals render has a tint in the stylesheet", () => {
  const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
  const states = [
    "routing_enabled", "ready_disabled", "disabled", "kyc_required", "account_required",
    "approval_required", "rate_invalid", "unknown_state",
  ].map((state) => payoutRoutingPill({ state }));
  for (const status of ["planned", "processed", "settled", "failed", "reversed"]) {
    states.push(transferStatusLabel({ status }));
  }
  for (const state of states) {
    const selector = `.state-${state.toLowerCase().replaceAll("_", "-")}`;
    assert.ok(css.includes(selector), `${selector} is rendered by the payout UI but has no stylesheet rule`);
  }
});
