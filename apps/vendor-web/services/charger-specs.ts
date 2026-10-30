// Charging capability is what route search filters on, so both portals show the same
// wording instead of each inventing its own summary of an incomplete setup.
export type ChargerSpecSource = {
  service_type: string;
  supported_connectors?: readonly string[] | null;
  max_power_kw?: string | number | null;
};

export type ChargerCapability = { summary: string; incomplete: boolean };

export function chargerCapability(service: ChargerSpecSource): ChargerCapability | null {
  if (service.service_type !== "charging") return null;
  const connectors = service.supported_connectors ?? [];
  const power = service.max_power_kw === null || service.max_power_kw === undefined ? null : Number(service.max_power_kw);
  const parts = [
    connectors.length ? connectors.join(" · ") : "no connectors",
    power !== null && Number.isFinite(power) && power > 0 ? `${power} kW` : "no kW",
  ];
  return { summary: parts.join(" · "), incomplete: !connectors.length || parts[1] === "no kW" };
}
