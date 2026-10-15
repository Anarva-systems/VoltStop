"use client";

import Link from "next/link";
import { AdminCard, AdminLoad, AdminPage, MetricCard, useAdminQuery, useAdminToken, formatAdminMoney } from "@/components/admin-ui";

type Point = { period: string; value: number | string };
type Overview = { metrics: Record<string, number | string | null>; bookings_over_time: Point[]; revenue_over_time: Point[]; vendor_growth: Point[]; booking_status: { status: string; value: number }[] };

function Chart({ title, points, currency = false }: { title: string; points: Point[]; currency?: boolean }) {
  if (!points.length) return <AdminCard title={title}><div className="admin-chart-empty">No recorded activity for this period.</div></AdminCard>;
  const max = Math.max(...points.map((point) => Number(point.value) || 0), 1);
  return <AdminCard title={title} subtitle="Actual database events"><div className="admin-chart">{points.map((point) => {
    const value = Number(point.value) || 0;
    return <div className="admin-chart-col" key={point.period} title={`${point.period}: ${currency ? formatAdminMoney(value) : value}`}><div className="admin-chart-bar" style={{ height: `${Math.max(3, value / max * 100)}%` }}/><span className="admin-chart-label">{new Date(point.period).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</span></div>;
  })}</div></AdminCard>;
}

export default function AdminOverviewPage() {
  const token = useAdminToken();
  const query = useAdminQuery<Overview>("/dashboard", token);
  const metrics = query.data?.metrics;
  const unavailable = "Unavailable";
  return <><AdminPage title="Platform overview" description="A live operational summary from VoltStop records. Values marked unavailable are not present in the current financial or routing schema."/>
    {query.loading ? <div className="admin-metric-grid">{Array.from({ length: 6 }, (_, index) => <MetricCard key={index} label="Loading" value="—" icon="chart"/>)}</div> : query.error ? <AdminLoad loading={false} error={query.error} data={null} retry={query.reload}>{() => null}</AdminLoad> : <>
      <div className="admin-metric-grid">
        <MetricCard label="Total bookings" value={metrics?.total_bookings ?? 0} icon="calendar" tone="cyan"/>
        <MetricCard label="Active vendors" value={metrics?.active_vendors ?? 0} icon="store" tone="green"/>
        <MetricCard label="Gross booking value" value={formatAdminMoney(metrics?.gross_booking_value)} note="Captured payments" icon="credit"/>
        <MetricCard label="Calculated commission" value={metrics?.platform_revenue === null ? unavailable : formatAdminMoney(metrics?.platform_revenue)} note={`${Number(metrics?.platform_commission_rate_bps ?? 0) / 100}% policy estimate · not provider-split`} icon="chart" tone="amber"/>
        <MetricCard label="Pending disputes" value={metrics?.pending_disputes ?? 0} icon="shield" tone="red"/>
        <MetricCard label="Refund amount" value={formatAdminMoney(metrics?.refund_amount)} note="Completed refunds only" icon="refresh"/>
      </div>
      <div className="admin-metric-grid">
        <MetricCard label="Today's bookings" value={metrics?.todays_bookings ?? 0} icon="calendar"/>
        <MetricCard label="Vendor applications" value={metrics?.pending_vendor_applications ?? 0} icon="inbox" tone="amber"/>
        <MetricCard label="Active routes" value={metrics?.active_routes === null ? unavailable : metrics?.active_routes ?? 0} note="Route telemetry is not stored" icon="pin"/>
        <MetricCard label="Open disputes" value={metrics?.open_disputes ?? 0} icon="shield" tone="red"/>
      </div>
      <div className="admin-grid-2"><Chart title="Bookings · 30 days" points={query.data?.bookings_over_time ?? []}/><Chart title="Captured revenue · 30 days" points={query.data?.revenue_over_time ?? []} currency/></div>
      <div className="admin-grid-2" style={{ marginTop: 15 }}><Chart title="Vendor growth · 12 months" points={query.data?.vendor_growth ?? []}/><AdminCard title="Booking status distribution"><div className="admin-legend">{(query.data?.booking_status ?? []).map((entry) => <span key={entry.status}><i/>{entry.status.replaceAll("_", " ")} · {entry.value}</span>)}</div>{!query.data?.booking_status.length && <div className="admin-chart-empty">No bookings recorded.</div>}</AdminCard></div>
      <div className="admin-actions" style={{ marginTop: 15 }}><Link className="button button-secondary" href="/admin/vendor-onboarding">Review vendor applications</Link><Link className="button button-secondary" href="/admin/bookings">Search bookings</Link><Link className="button button-secondary" href="/admin/live-operations">Open corridor operations</Link></div>
    </>}
  </>;
}
