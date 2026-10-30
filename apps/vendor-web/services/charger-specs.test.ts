import assert from "node:assert/strict";
import { test } from "node:test";
import { chargerCapability } from "./charger-specs.ts";

test("only charging services carry a capability summary", () => {
  assert.equal(chargerCapability({ service_type: "hotel_room" }), null);
  assert.equal(chargerCapability({ service_type: "restaurant_table", supported_connectors: ["CCS2"] }), null);
});

test("a fully configured charger reads as plug types and peak power", () => {
  const result = chargerCapability({ service_type: "charging", supported_connectors: ["CCS2", "CHAdeMO"], max_power_kw: 60 });
  assert.deepEqual(result, { summary: "CCS2 · CHAdeMO · 60 kW", incomplete: false });
});

test("decimal power arrives as a string and still reads as kW", () => {
  const result = chargerCapability({ service_type: "charging", supported_connectors: ["Type 2"], max_power_kw: "22.00" });
  assert.equal(result?.summary, "Type 2 · 22 kW");
  assert.equal(result?.incomplete, false);
});

test("a charger with no plug types is flagged so reviewers see the routing gap", () => {
  const missingConnectors = chargerCapability({ service_type: "charging", supported_connectors: [], max_power_kw: 120 });
  assert.equal(missingConnectors?.summary, "no connectors · 120 kW");
  assert.equal(missingConnectors?.incomplete, true);

  const missingPower = chargerCapability({ service_type: "charging", supported_connectors: ["CCS2"], max_power_kw: null });
  assert.equal(missingPower?.summary, "CCS2 · no kW");
  assert.equal(missingPower?.incomplete, true);

  const legacyRow = chargerCapability({ service_type: "charging", supported_connectors: null, max_power_kw: undefined });
  assert.equal(legacyRow?.incomplete, true);
});
