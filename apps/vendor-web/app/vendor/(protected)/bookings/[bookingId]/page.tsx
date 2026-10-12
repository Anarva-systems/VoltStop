"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { apiPost } from "@/services/api";
import { Button, ErrorState, formatDate, formatMoney, formatTime, Icon, PageHeader, Panel, SectionHeading, Skeleton, StatePill, toast, useAccessToken, useVendorQuery } from "@/components/portal";
import type { VendorBooking } from "@/types/vendor";

const eventNames: Record<string, string> = {
  created: "Booking placed",
  payment_started: "Payment started",
  payment_success: "Payment verified",
  payment_failed: "Payment failed",
  confirmed: "Reservation confirmed",
  cancelled: "Reservation cancelled",
  expired: "Reservation expired",
  completed: "Visit completed",
  vendor_accepted: "Acknowledged by your business",
  vendor_completed: "Marked complete by your business",
};

export default function VendorBookingDetailPage() {
  const { bookingId } = useParams<{ bookingId: string }>();
  const token = useAccessToken();
  const bookingState = useVendorQuery<VendorBooking>(`/bookings/${bookingId}`, token);
  const [busy, setBusy] = useState(false);
  const booking = bookingState.data;
  const canAccept = booking?.status === "confirmed" && booking.payment_status === "captured" && booking.webhook_verified && booking.vendor_acknowledgement === "pending";
  const canComplete = booking?.status === "confirmed" && booking.payment_status === "captured" && booking.vendor_acknowledgement === "accepted";

  async function act(action: "accept" | "complete") {
    if (!token || !booking) return;
    setBusy(true);
    try {
      await apiPost(`/bookings/${booking.booking_id}/${action}`, token);
      toast(action === "accept" ? "Booking accepted" : "Booking marked complete");
      bookingState.reload();
    } catch (reason) { toast(reason instanceof Error ? reason.message : "Could not update booking"); }
    finally { setBusy(false); }
  }

  return <>
    <PageHeader eyebrow="RESERVATION RECORD" title="Booking details" description="Customer and payment information attached to this vendor-owned reservation." action={<Link className="button button-secondary" href="/vendor/bookings"><Icon name="arrow"/>Back to bookings</Link>}/>
    {bookingState.loading ? <Panel className="panel-pad"><Skeleton rows={10}/></Panel> : bookingState.error ? <Panel><ErrorState message={bookingState.error} onRetry={bookingState.reload}/></Panel> : booking && <div className="booking-layout">
      <div className="dashboard-column">
        <Panel className="panel-pad">
          <div className="detail-title"><div><h2>Reservation {booking.booking_id.slice(0, 8).toUpperCase()}</h2><p>{booking.booking_id}</p></div><StatePill value={booking.status}/></div>
          <div className="detail-grid">
            <Field label="Customer" value={booking.customer_name || "VoltStop driver"}/>
            <Field label="Phone" value={booking.customer_phone || "Not available"}/>
            <Field label="Vehicle" value={booking.ev_model || "Not provided"}/>
            <Field label="Battery" value={booking.battery_kwh ? `${booking.battery_kwh} kWh` : "Not provided"}/>
            <Field label="Business" value={booking.vendor_name || "Your business"}/>
            <Field label="Service" value={booking.service_name}/>
            <Field label="Slot ID" value={booking.slot_id}/>
            <Field label="Slot capacity" value={booking.capacity}/>
            <Field label="Date" value={formatDate(booking.slot_start_time)}/>
            <Field label="Time" value={`${formatTime(booking.slot_start_time)} – ${formatTime(booking.slot_end_time)}`}/>
            <Field label="Amount" value={formatMoney(booking.charged_amount_inr ?? booking.amount_inr)}/>
            <Field label="Payment status" value={booking.payment_status ?? "Not started"}/>
            <Field label="Vendor acknowledgement" value={booking.vendor_acknowledgement}/>
            <Field label="Created at" value={formatDate(booking.created_at, { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" })}/>
          </div>
          <div className="form-actions" style={{ justifyContent: "flex-start" }}>
            {canAccept && <Button disabled={busy} onClick={() => act("accept")}>{busy ? "Saving…" : "Accept booking"}</Button>}
            {canComplete && <Button disabled={busy} onClick={() => act("complete")}>{busy ? "Saving…" : "Mark completed"}</Button>}
            {!canAccept && !canComplete && <div className="verification-state"><Icon name="check" size={15}/>{booking.status === "confirmed" && booking.vendor_acknowledgement === "accepted" ? "Your team has accepted this paid booking." : booking.status === "confirmed" ? "Booking actions are waiting for verified payment." : "No vendor action is available in this booking state."}</div>}
          </div>
          <p className="label-note" style={{ marginTop: 13 }}>Only the server-verified Razorpay payment state can unlock vendor acknowledgement. Payment state cannot be edited here.</p>
        </Panel>
        <Panel className="panel-pad"><SectionHeading title="Booking timeline" detail="Events recorded by VoltStop"/>
          {!booking.timeline?.length ? <p className="page-description">No booking events were returned.</p> : <div className="timeline">{booking.timeline.map((event, index) => <div className="timeline-row" key={`${event.event_type}-${index}`}><span className="timeline-dot"/><div><strong>{eventNames[event.event_type] ?? event.event_type.replaceAll("_", " ")}</strong><span>{formatDate(event.created_at, { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" })}</span></div></div>)}</div>}
        </Panel>
      </div>
      <Panel className="panel-pad detail-card">
        <SectionHeading title="Reservation status"/>
        <div className="detail-grid"><Field label="Booking" value={<StatePill value={booking.status}/>}/><Field label="Payment" value={<StatePill value={booking.payment_status ?? "pending"}/>}/><Field label="Vendor response" value={<StatePill value={booking.vendor_acknowledgement}/>}/><Field label="Verified" value={booking.webhook_verified ? "Webhook confirmed" : "Waiting for provider"}/></div>
        <div className="warning-copy" style={{ marginTop: 20 }}>{booking.payment_status === "captured" ? "Payment is confirmed by the Razorpay webhook." : "Never ask a driver to rely on a client-side payment success screen. Wait for server confirmation."}</div>
        <div style={{ marginTop: 18 }}><Link className="action-link" href="/vendor/requests">Open request inbox <Icon name="arrow" size={13}/></Link></div>
      </Panel>
    </div>}
  </>;
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="detail-field"><span>{label}</span><strong>{value}</strong></div>;
}
