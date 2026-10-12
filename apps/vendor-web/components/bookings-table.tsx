"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { apiPost } from "@/services/api";
import { Button, EmptyState, ErrorState, formatDate, formatMoney, formatTime, Icon, Panel, Skeleton, StatePill, toast, useVendorQuery } from "@/components/portal";
import type { VendorBooking } from "@/types/vendor";

export function VendorBookingsTable({ token, onlyRequests = false }: { token: string | null; onlyRequests?: boolean }) {
  const bookings = useVendorQuery<VendorBooking[]>("/bookings", token);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [busy, setBusy] = useState("");
  const filtered = useMemo(() => (bookings.data ?? []).filter((booking) => {
    const requestMatches = !onlyRequests || (booking.status === "confirmed" && booking.vendor_acknowledgement === "pending" && booking.payment_status === "captured" && booking.webhook_verified);
    const statusMatches = status === "all" || booking.status === status;
    const searchMatches = !query || `${booking.booking_id} ${booking.customer_name} ${booking.ev_model ?? ""} ${booking.service_name}`.toLowerCase().includes(query.toLowerCase());
    return requestMatches && statusMatches && searchMatches;
  }), [bookings.data, onlyRequests, query, status]);

  async function accept(bookingId: string) {
    if (!token) return;
    setBusy(bookingId);
    try { await apiPost(`/bookings/${bookingId}/accept`, token); bookings.reload(); }
    catch (reason) { toast(reason instanceof Error ? reason.message : "Could not accept booking"); }
    finally { setBusy(""); }
  }

  if (bookings.loading) return <Panel className="panel-pad"><Skeleton rows={8}/></Panel>;
  if (bookings.error) return <Panel><ErrorState message={bookings.error} onRetry={bookings.reload}/></Panel>;

  return <Panel className="table-panel">
    <div className="table-toolbar">
      <label className="search-box"><Icon name="search" size={16}/><input aria-label="Search bookings" placeholder="Search ID, customer, vehicle…" value={query} onChange={(event) => setQuery(event.target.value)}/></label>
      <div className="filter-row">
        {!onlyRequests && <select className="select-control" style={{ width: "auto", minWidth: 145 }} aria-label="Filter by booking status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">All statuses</option><option value="pending">Pending payment</option><option value="confirmed">Confirmed</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option><option value="expired">Expired</option></select>}
        <Button variant="secondary" onClick={bookings.reload}><Icon name="refresh"/>Refresh</Button>
      </div>
    </div>
    {!filtered.length ? <EmptyState title={query ? "No matching bookings" : onlyRequests ? "No requests need your attention" : "No bookings yet"} description={query ? "Try a different booking ID, customer, or vehicle." : onlyRequests ? "Paid reservations waiting for acknowledgement will appear here." : "Driver reservations will appear here after they book a time at your business."}/> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Booking ID</th><th>Customer</th><th>EV model</th><th>Date</th><th>Time</th><th>Service</th><th>Amount</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody>{filtered.map((booking) => <tr key={booking.booking_id}>
        <td><span className="table-primary">{booking.booking_id.slice(0, 8).toUpperCase()}</span><span className="table-secondary">{booking.booking_id}</span></td>
        <td><span className="table-primary">{booking.customer_name || "VoltStop driver"}</span><span className="table-secondary">{booking.customer_phone || "Phone private"}</span></td>
        <td>{booking.ev_model || "—"}</td>
        <td>{formatDate(booking.slot_start_time, { day: "numeric", month: "short", year: "numeric" })}</td>
        <td>{formatTime(booking.slot_start_time)}<span className="table-secondary">to {formatTime(booking.slot_end_time)}</span></td>
        <td>{booking.service_name}</td>
        <td className="table-primary">{formatMoney(booking.charged_amount_inr ?? booking.amount_inr)}</td>
        <td><StatePill value={booking.vendor_acknowledgement === "accepted" && booking.status === "confirmed" ? "accepted" : booking.status}/></td>
        <td><div className="table-actions"><Link className="action-link" href={`/vendor/bookings/${booking.booking_id}`}>View <Icon name="arrow" size={13}/></Link>{onlyRequests && <Button disabled={busy === booking.booking_id} onClick={() => accept(booking.booking_id)}>{busy === booking.booking_id ? "Saving…" : "Accept"}</Button>}</div></td>
      </tr>)}</tbody></table></div>}
    <div className="table-toolbar" style={{ borderTop: "1px solid var(--line)", color: "var(--muted)", fontSize: 10 }}>{filtered.length} {filtered.length === 1 ? "booking" : "bookings"}<span>Customer details are limited to bookings for your business.</span></div>
  </Panel>;
}
