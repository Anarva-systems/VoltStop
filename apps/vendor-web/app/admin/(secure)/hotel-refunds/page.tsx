"use client";

import { useState } from "react";
import { adminPost } from "@/services/admin-api";
import { toast } from "@/components/portal";
import { AdminButton, AdminCard, AdminLoad, AdminPage, AdminTable, FilterSelect, StateBadge, formatAdminDate, formatAdminMoney, useAdminQuery, useAdminToken } from "@/components/admin-ui";

type HotelRefund = { id: string; reservation_id: string; amount_inr: string; reason: string; status: string; provider_status: string | null; provider_error: string | null; created_at: string; vendor_name: string; room_name: string; customer_id: string; check_in: string; check_out: string; reservation_status: string; payment_status: string; webhook_verified: boolean; razorpay_payment_id: string };
type Results = { items: HotelRefund[]; total: number };
type AdminMe = { permissions: string[] };
type Decision = { refund: HotelRefund; action: "approve" | "reject" };

export default function HotelRefundsPage() {
  const token = useAdminToken();
  const [status, setStatus] = useState("");
  const [decision, setDecision] = useState<Decision | null>(null);
  const [reason, setReason] = useState("");
  const [phrase, setPhrase] = useState("");
  const [busy, setBusy] = useState(false);
  const me = useAdminQuery<AdminMe>("/me", token);
  const canApprove = Boolean(me.data?.permissions.includes("refunds:approve"));
  const params = new URLSearchParams({ limit: "100" }); if (status) params.set("status", status);
  const query = useAdminQuery<Results>(`/hotel-refunds?${params}`, token);

  async function decide(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!token || !decision || (decision.action === "approve" && phrase !== "REFUND")) return;
    setBusy(true);
    try {
      await adminPost(`/hotel-refunds/${decision.refund.id}/${decision.action}`, token, { reason });
      toast(decision.action === "approve" ? "Refund submitted to Razorpay" : "Refund request rejected");
      setDecision(null); setReason(""); setPhrase(""); query.reload();
    } catch (error) { toast(error instanceof Error ? error.message : "Refund decision could not be completed"); query.reload(); }
    finally { setBusy(false); }
  }

  return <>
    <AdminPage title="Hotel cancellation refunds" description="Customer cancellations are reviewed separately. The server verifies captured payment and amount, then waits for Razorpay webhook confirmation before marking a refund complete."/>
    <AdminCard>
      <div className="admin-toolbar"><FilterSelect value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All hotel refund states</option>{["requested", "approved", "processing", "completed", "failed", "rejected"].map((item) => <option key={item}>{item}</option>)}</FilterSelect></div>
      <AdminLoad loading={query.loading} error={query.error} data={query.data} retry={query.reload} empty={Boolean(query.data && !query.data.items.length)} emptyTitle="No hotel refund requests">
        {(data) => <AdminTable headers={["Request", "Reservation", "Hotel / room", "Stay", "Customer", "Amount", "State", "Provider", "Created", "Action"]}>{data.items.map((row) => <tr key={row.id}>
          <td className="primary-cell">{row.id.slice(0, 12)}…</td><td>{row.reservation_id.slice(0, 12)}…<small style={{ display: "block" }}>{row.reservation_status}</small></td>
          <td>{row.vendor_name}<small style={{ display: "block" }}>{row.room_name}</small></td><td>{formatAdminDate(row.check_in)} – {formatAdminDate(row.check_out)}</td>
          <td>{row.customer_id.slice(0, 12)}…</td><td>{formatAdminMoney(row.amount_inr)}</td><td><StateBadge value={row.status}/></td>
          <td>{row.provider_status ?? "Awaiting finance"}{row.provider_error && <small style={{ display: "block", color: "#f6c453" }}>Needs reconciliation</small>}</td>
          <td>{formatAdminDate(row.created_at, true)}</td><td>{row.status === "requested" && canApprove ? <div className="admin-toolbar"><AdminButton onClick={() => { setDecision({ refund: row, action: "approve" }); setReason(""); }}>Approve &amp; issue</AdminButton><AdminButton variant="danger" onClick={() => { setDecision({ refund: row, action: "reject" }); setReason(""); }}>Reject</AdminButton></div> : "—"}</td>
        </tr>)}</AdminTable>}
      </AdminLoad>
    </AdminCard>
    {decision && <div className="admin-modal-backdrop"><form className="admin-modal" onSubmit={decide} role="dialog" aria-modal="true">
      <div className="admin-modal-head"><h2>{decision.action === "approve" ? "Approve hotel refund" : "Reject hotel refund"}</h2><button type="button" className="admin-modal-close" onClick={() => setDecision(null)}>×</button></div>
      <p>{decision.action === "approve" ? "The backend checks the verified captured payment and refundable amount before submitting the refund. Unknown provider responses require reconciliation." : "This rejects the request. No payment provider call will be made."}</p>
      <div className="admin-callout">{formatAdminMoney(decision.refund.amount_inr)} · {decision.refund.vendor_name} · {decision.refund.room_name}<br/>Reservation {decision.refund.reservation_id.slice(0, 12)}… · payment {decision.refund.payment_status} · webhook verified: {decision.refund.webhook_verified ? "yes" : "no"}</div>
      <label className="admin-reason">Finance decision reason<textarea className="admin-filter" required minLength={8} maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} /></label>
      {decision.action === "approve" && <label className="admin-reason">Type REFUND to authorize provider submission<input className="admin-filter" required value={phrase} onChange={(event) => setPhrase(event.target.value)} placeholder="REFUND"/></label>}
      <div className="admin-modal-actions"><button className="button button-secondary" type="button" disabled={busy} onClick={() => setDecision(null)}>Cancel</button><AdminButton variant="danger" type="submit" busy={busy} disabled={decision.action === "approve" && phrase !== "REFUND"}>{decision.action === "approve" ? "Approve & issue" : "Reject request"}</AdminButton></div>
    </form></div>}
  </>;
}
