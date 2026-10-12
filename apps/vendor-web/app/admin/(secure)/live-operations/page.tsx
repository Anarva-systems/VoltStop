"use client";

import { AdminCard, AdminLoad, AdminPage, AdminTable, StateBadge, formatAdminDate, useAdminQuery, useAdminToken } from "@/components/admin-ui";

type Operation = { vendor_id: string; name: string; type: string; address: string; lat: number; lng: number; is_active: boolean; is_verified: boolean; verification_status: string; capacity: number; active_bookings: number; held_locks: number; next_available_slot: string | null };
function operationalStatus(vendor: Operation) {
  if (["pending","under_review","changes_requested","rejected","suspended"].includes(vendor.verification_status)) return vendor.verification_status === "suspended" ? "temporarily_closed" : "under_review";
  if (Number(vendor.capacity) > 0 && (Number(vendor.active_bookings) > 0 || Number(vendor.held_locks) > 0)) return "limited_capacity";
  if (Number(vendor.capacity) <= 0 && (Number(vendor.active_bookings) > 0 || Number(vendor.held_locks) > 0)) return "fully_booked";
  if (!vendor.is_active) return "temporarily_closed";
  return "operational";
}
export default function LiveOperationsPage() {
  const token = useAdminToken(); const query = useAdminQuery<Operation[]>("/live-operations", token);
  return <><AdminPage title="Live operations" description="Pilot corridor service capacity calculated from vendor slots and active bookings. No GPS or vehicle telemetry is available in the current platform."/><div className="admin-callout" style={{marginBottom:14}}>Srikakulam ⇄ Vijayawada <span>· Capacity reflects stored slot inventory; GPS and roadside telemetry are not connected.</span></div>
    <AdminLoad loading={query.loading} error={query.error} data={query.data} retry={query.reload} empty={Boolean(query.data && !query.data.length)} emptyTitle="No corridor vendors recorded">{(items) => <AdminCard><AdminTable headers={["Pitstop","Location","Type","Operational state","Available capacity","Active bookings","Lock holds","Next available","Stored location"]}>{items.map((vendor) => <tr key={vendor.vendor_id}><td className="primary-cell">{vendor.name}</td><td>{vendor.address}</td><td>{vendor.type}</td><td><StateBadge value={operationalStatus(vendor)}/></td><td>{vendor.capacity}</td><td>{vendor.active_bookings}</td><td>{vendor.held_locks}</td><td>{formatAdminDate(vendor.next_available_slot,true)}</td><td>{vendor.lat.toFixed(4)}, {vendor.lng.toFixed(4)}</td></tr>)}</AdminTable></AdminCard>}</AdminLoad>
  </>;
}
