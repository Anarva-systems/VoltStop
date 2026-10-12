"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { adminPost } from "@/services/admin-api";
import { toast } from "@/components/portal";
import { AdminActionDialog, AdminButton, AdminCard, AdminLoad, AdminPage, AdminTable, FilterInput, FilterSelect, StateBadge, formatAdminDate, formatAdminMoney, useAdminQuery, useAdminToken } from "@/components/admin-ui";

type Vendor = { id: string; name: string; type: string; address: string; verification_status: string; current_stage: string; completed_stages: string[]; submitted_at: string; is_active: boolean; bookings: number; gross_revenue: string | null; created_at: string };
type PageData = { items: Vendor[]; total: number; limit: number; offset: number };

export function AdminVendorList({ onboarding = false }: { onboarding?: boolean }) {
  const token = useAdminToken();
  const [search, setSearch] = useState(""); const [status, setStatus] = useState(""); const [type, setType] = useState(""); const [location, setLocation] = useState(""); const [page, setPage] = useState(0);
  const [target, setTarget] = useState<{ vendor: Vendor; action: string } | null>(null); const [busy, setBusy] = useState(false);
  const query = useMemo(() => {
    const params = new URLSearchParams({ limit: "25", offset: String(page * 25) });
    if (search) params.set("search", search); if (status) params.set("status", status); if (type && !onboarding) params.set("type", type); if (location && !onboarding) params.set("location", location);
    return `${onboarding ? "/vendor-onboarding" : "/vendors"}?${params}`;
  }, [location, onboarding, page, search, status, type]);
  const data = useAdminQuery<PageData>(query, token);
  async function act(reason: string) {
    if (!target || !token) return; setBusy(true);
    try {
      await adminPost(`/vendor${onboarding ? "-onboarding" : "s"}/${target.vendor.id}/action`, token, { action: target.action, reason });
      toast(`Vendor ${target.action.replaceAll("_", " ")} recorded`); setTarget(null); data.reload();
    } catch (error) { toast(error instanceof Error ? error.message : "Vendor action failed"); }
    finally { setBusy(false); }
  }
  const title = onboarding ? "Vendor onboarding" : "Vendors";
  return <><AdminPage eyebrow={onboarding ? "VENDOR REVIEW" : "NETWORK MANAGEMENT"} title={title} description={onboarding ? "Review application details and record every approval decision with a reason." : "Search the partner network, inspect operations, and manage vendor status."}/>
    <AdminCard>
      <div className="admin-toolbar"><FilterInput className="admin-search" placeholder="Search business or address" value={search} onChange={(event) => { setPage(0); setSearch(event.target.value); }}/><FilterSelect value={status} onChange={(event) => { setPage(0); setStatus(event.target.value); }}><option value="">All statuses</option>{["pending","under_review","changes_requested","approved","rejected","suspended"].map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</FilterSelect>{!onboarding && <><FilterSelect value={type} onChange={(event) => { setPage(0); setType(event.target.value); }}><option value="">All types</option><option value="restaurant">Restaurant</option><option value="hotel">Hotel</option></FilterSelect><FilterInput placeholder="Location contains" value={location} onChange={(event) => { setPage(0); setLocation(event.target.value); }}/></>}<span className="admin-role-chip">{data.data?.total ?? "—"} records</span></div>
      <AdminLoad loading={data.loading} error={data.error} data={data.data} retry={data.reload} empty={Boolean(data.data && !data.data.items.length)} emptyTitle="No matching vendors">{(pageData) => <><AdminTable headers={["Vendor","Type","Location",...(onboarding?["Review stage"]:[]),"Verification","Status","Bookings","Gross revenue","Created","Actions"]}>
        {pageData.items.map((vendor) => <tr key={vendor.id}><td className="primary-cell"><Link href={`/admin/vendors/${vendor.id}`}>{vendor.name}</Link><small style={{ display:"block", color:"#8194a8", marginTop:4 }}>{vendor.id.slice(0,8)}…</small></td><td>{vendor.type}</td><td className="muted-cell">{vendor.address}</td>{onboarding&&<td>{vendor.current_stage?.replaceAll("_"," ")??"application"}<small style={{display:"block",color:"#8194a8",marginTop:4}}>{vendor.completed_stages?.length??0} stages complete</small></td>}<td><StateBadge value={vendor.verification_status}/></td><td><StateBadge value={vendor.is_active ? "active" : "inactive"}/></td><td>{vendor.bookings}</td><td>{formatAdminMoney(vendor.gross_revenue)}</td><td>{formatAdminDate(vendor.submitted_at??vendor.created_at)}</td><td><div className="admin-actions"><Link className="button button-quiet" href={`/admin/vendors/${vendor.id}`}>View</Link>{vendor.verification_status === "approved" ? <AdminButton variant="danger" onClick={() => setTarget({ vendor, action: "suspend" })}>Suspend</AdminButton> : ["pending","under_review","changes_requested"].includes(vendor.verification_status) && <><AdminButton onClick={() => setTarget({ vendor, action: "approve" })}>Approve</AdminButton><AdminButton variant="secondary" onClick={() => setTarget({ vendor, action: "request_changes" })}>Request changes</AdminButton><AdminButton variant="danger" onClick={() => setTarget({ vendor, action: "reject" })}>Reject</AdminButton></>}{vendor.verification_status === "suspended" && <AdminButton onClick={() => setTarget({ vendor, action: "reactivate" })}>Reactivate</AdminButton>}</div></td></tr>)}
      </AdminTable><div className="admin-pager"><span>Showing {pageData.offset + 1}–{Math.min(pageData.offset + pageData.items.length, pageData.total)} of {pageData.total}</span><button disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))}>Previous</button><button disabled={pageData.offset + pageData.items.length >= pageData.total} onClick={() => setPage((value) => value + 1)}>Next</button></div></>}</AdminLoad>
    </AdminCard>
    {target && <AdminActionDialog title={`${target.action.replaceAll("_", " ")} · ${target.vendor.name}`} description={`Confirm the ${target.action.replaceAll("_", " ")} decision for ${target.vendor.name}. This will update the server-side vendor state.`} impact={`Current verification: ${target.vendor.verification_status}. Every decision is written to the immutable audit log.`} confirmLabel={target.action.replaceAll("_", " ")} busy={busy} onClose={() => setTarget(null)} onConfirm={act}/>}
  </>;
}
