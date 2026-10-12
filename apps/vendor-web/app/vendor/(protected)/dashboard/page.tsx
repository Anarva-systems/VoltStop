"use client";

import Link from "next/link";
import { useState } from "react";
import { apiPost } from "@/services/api";
import { Button, ErrorState, formatDate, formatMoney, formatTime, Icon, PageHeader, Panel, SectionHeading, Skeleton, StatePill, toast, useAccessToken, useVendorQuery } from "@/components/portal";
import type { VendorDashboard } from "@/types/vendor";

const events: Record<string, string> = {
  created: "A booking was placed",
  slot_locked: "A slot was temporarily held",
  payment_started: "Payment was started",
  payment_success: "Payment was verified",
  payment_failed: "Payment did not complete",
  confirmed: "Booking confirmed",
  cancelled: "Booking cancelled",
  expired: "Booking expired",
  completed: "Booking completed",
  vendor_accepted: "Booking accepted by your team",
  vendor_completed: "Visit marked complete",
};

export default function VendorDashboardPage() {
  const token = useAccessToken();
  const dashboard = useVendorQuery<VendorDashboard>("/dashboard", token);
  const [actionBusy, setActionBusy] = useState("");

  async function accept(bookingId: string) {
    if (!token) return;
    setActionBusy(bookingId);
    try {
      await apiPost(`/bookings/${bookingId}/accept`, token);
      toast("Booking accepted");
      dashboard.reload();
    } catch (reason) { toast(reason instanceof Error ? reason.message : "Could not accept booking"); }
    finally { setActionBusy(""); }
  }

  return <>
    <div className="dashboard-greeting"><span/>DAILY OPERATIONS · {formatDate(new Date(), { weekday: "long", day: "numeric", month: "long" })}</div>
    <PageHeader title="Your highway stop, at a glance" description="Bookings and service activity for your VoltStop location." action={<Button variant="secondary" onClick={dashboard.reload}><Icon name="refresh"/>Refresh</Button>}/>
    {dashboard.loading ? <><div className="metric-grid">{Array.from({ length: 4 }, (_, index) => <Panel key={index} className="panel-pad"><Skeleton rows={2}/></Panel>)}</div><div className="dashboard-grid"><Panel className="panel-pad"><Skeleton rows={7}/></Panel><Panel className="panel-pad"><Skeleton rows={6}/></Panel></div></> : dashboard.error ? <Panel><ErrorState message={dashboard.error} onRetry={dashboard.reload}/>{dashboard.error.includes("No vendor profile is linked to this account") && <div style={{ padding: "0 24px 22px", display: "flex", justifyContent: "center" }}><Link className="button button-primary" href="/vendor/profile">Set up business profile <Icon name="arrow" size={14}/></Link></div>}</Panel> : dashboard.data && <>
      <div className="metric-grid">
        <Metric title="Pending Requests" value={dashboard.data.metrics.pending_requests} note="Paid bookings awaiting your response" icon="inbox" tone="cyan"/>
        <Metric title="Today’s Bookings" value={dashboard.data.metrics.todays_bookings} note="Reservations scheduled today" icon="calendar" tone="green"/>
        <Metric title="Available Capacity" value={dashboard.data.metrics.available_capacity} note="Places open across today’s slots" icon="bolt" tone="cyan"/>
        <Metric title="Today’s Revenue" value={formatMoney(dashboard.data.metrics.todays_revenue)} note="Captured payments, server reported" icon="chart" tone="green"/>
      </div>
      <div className="dashboard-grid">
        <div className="dashboard-column">
          <Panel className="panel-pad">
            <SectionHeading title="Today’s schedule" detail="Reservations in local server time" action={<Link className="action-link" href="/vendor/bookings">All bookings <Icon name="arrow" size={14}/></Link>}/>
            {dashboard.data.schedule.length === 0 ? <div className="state-box"><span className="state-icon"><Icon name="calendar"/></span><h3>No bookings scheduled today</h3><p>New paid reservations will appear here when drivers book your stop.</p></div> : <div className="schedule-list">{dashboard.data.schedule.map((booking) => <div className="schedule-row" key={booking.booking_id}>
              <div className="time-block">{formatTime(booking.slot_start_time)}<span className="table-secondary">{formatTime(booking.slot_end_time)}</span></div>
              <div><div className="schedule-name">{booking.customer_name || "VoltStop driver"}</div><div className="schedule-meta">{booking.service_type.replaceAll("_", " ")} · {formatMoney(booking.amount_inr)}</div></div>
              <Link href={`/vendor/bookings/${booking.booking_id}`}><StatePill value={booking.vendor_acknowledgement === "accepted" ? booking.status : "pending"}/></Link>
            </div>)}</div>}
          </Panel>
          <Panel className="panel-pad">
            <SectionHeading title="Recent activity" detail="Latest booking events from the platform"/>
            {dashboard.data.activity.length === 0 ? <p className="page-description">Activity will appear here as bookings move through their lifecycle.</p> : <div className="activity-list">{dashboard.data.activity.map((item) => <div key={item.id} className="activity-row"><span className="activity-mark"><Icon name={item.event_type.includes("payment") ? "check" : "calendar"} size={14}/></span><div className="activity-copy">{events[item.event_type] ?? item.event_type.replaceAll("_", " ")}<small>Booking {item.booking_id.slice(0, 8)} · {formatDate(item.created_at, { hour: "numeric", minute: "2-digit", day: "numeric", month: "short" })}</small></div></div>)}</div>}
          </Panel>
        </div>
        <div className="dashboard-column">
          <Panel className="panel-pad">
            <SectionHeading title="Incoming requests" detail="Payment-confirmed bookings waiting for acknowledgement" action={<Link className="action-link" href="/vendor/requests">View all <Icon name="arrow" size={14}/></Link>}/>
            {dashboard.data.requests.length === 0 ? <div className="state-box"><span className="state-icon"><Icon name="inbox"/></span><h3>You’re all caught up</h3><p>New confirmed requests will appear here.</p></div> : <div className="request-list">{dashboard.data.requests.map((item) => <div className="request-row" key={item.booking_id}>
              <div className="schedule-row" style={{ gridTemplateColumns: "1fr auto", gap: 8 }}><div><div className="schedule-name">{item.customer_name || "VoltStop driver"}</div><div className="schedule-meta">{formatDate(item.slot_start_time, { day: "numeric", month: "short" })} · {formatTime(item.slot_start_time)} · {formatMoney(item.amount_inr)}</div></div><StatePill value={item.payment_status ?? "pending"}/></div>
              <div className="table-actions" style={{ paddingBottom: 12 }}><Link className="action-link" href={`/vendor/bookings/${item.booking_id}`}>View</Link><Button disabled={actionBusy === item.booking_id} onClick={() => accept(item.booking_id)}>{actionBusy === item.booking_id ? "Saving…" : "Accept"}</Button></div>
            </div>)}</div>}
            <p className="label-note" style={{ marginTop: 12 }}>Requests are shown after secure payment confirmation. Rejections and refunds are not enabled by the current booking lifecycle.</p>
          </Panel>
          <Panel className="panel-pad">
            <SectionHeading title="Availability summary" detail="Today’s open slot capacity" action={<Link className="action-link" href="/vendor/availability">Manage <Icon name="arrow" size={14}/></Link>}/>
            <div className="availability-summary"><div className="availability-caption"><span>Open capacity</span><strong>{dashboard.data.metrics.available_capacity}</strong></div><div className="availability-bar"><span style={{ width: dashboard.data.metrics.available_capacity ? "100%" : "0%" }}/></div><div className="mini-stats"><div className="mini-stat"><strong>{dashboard.data.schedule.length}</strong><span>BOOKINGS TODAY</span></div><div className="mini-stat"><strong>{dashboard.data.requests.length}</strong><span>NEED ACKNOWLEDGEMENT</span></div><div className="mini-stat"><strong>{dashboard.data.metrics.available_capacity}</strong><span>PLACES OPEN</span></div></div></div>
          </Panel>
        </div>
      </div>
    </>}
  </>;
}

function Metric({ title, value, note, icon, tone }: { title: string; value: string | number; note: string; icon: string; tone: "green" | "cyan" }) {
  return <div className="metric-card"><div className="metric-top"><span>{title}</span><span className="metric-icon" style={{ color: tone === "green" ? "var(--green)" : "var(--cyan)" }}><Icon name={icon}/></span></div><strong>{value}</strong><div className="metric-note">{note}</div></div>;
}
