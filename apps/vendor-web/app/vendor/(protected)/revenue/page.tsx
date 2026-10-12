"use client";

import { Button, ErrorState, formatMoney, Icon, PageHeader, Panel, SectionHeading, Skeleton, useAccessToken, useVendorQuery } from "@/components/portal";
import type { RevenueReport } from "@/types/vendor";

export default function VendorRevenuePage() {
  const token = useAccessToken();
  const report = useVendorQuery<RevenueReport>("/revenue", token);
  return <>
    <PageHeader eyebrow="SETTLEMENT VIEW" title="Revenue" description="Totals reflect captured payments returned by the backend. No platform commission is assumed." action={<Button variant="secondary" onClick={report.reload}><Icon name="refresh"/>Refresh</Button>}/>
    {report.loading ? <><Panel className="panel-pad"><Skeleton rows={4}/></Panel><div className="revenue-stat-grid">{[1,2,3].map((item) => <Panel key={item} className="panel-pad"><Skeleton rows={2}/></Panel>)}</div></> : report.error ? <Panel><ErrorState message={report.error} onRetry={report.reload}/></Panel> : report.data && <>
      <div className="revenue-hero"><div><span>Today · captured payments</span><strong>{formatMoney(report.data.today_gross)}</strong><small>Based on server-confirmed Razorpay status</small></div><span className="metric-icon"><Icon name="chart" size={24}/></span></div>
      <div className="revenue-stat-grid"><Panel className="revenue-stat"><span>This week · captured</span><strong>{formatMoney(report.data.week_gross)}</strong></Panel><Panel className="revenue-stat"><span>This month · captured</span><strong>{formatMoney(report.data.month_gross)}</strong></Panel><Panel className="revenue-stat"><span>All-time bookings</span><strong>{report.data.total_bookings}</strong></Panel></div>
      <Panel className="panel-pad"><SectionHeading title="Booking outcomes" detail="Derived from your vendor-scoped booking records"/><div className="mini-stats"><div className="mini-stat"><strong>{report.data.completed_bookings}</strong><span>COMPLETED</span></div><div className="mini-stat"><strong>{report.data.cancelled_bookings}</strong><span>CANCELLED</span></div><div className="mini-stat"><strong>{report.data.refunded_payments}</strong><span>REFUNDED PAYMENTS</span></div></div>
        <div className="warning-copy" style={{ marginTop: 17 }}>Refund totals are not included in revenue because the current API records refund status, but does not yet provide a vendor-facing refund ledger. Payment reversals remain server and provider managed.</div>
      </Panel>
      <p className="label-note" style={{ marginTop: 14 }}>Gross amounts are reported as captured by Razorpay. Platform fees and vendor payout are omitted because no commission schedule is configured.</p>
    </>}
  </>;
}
