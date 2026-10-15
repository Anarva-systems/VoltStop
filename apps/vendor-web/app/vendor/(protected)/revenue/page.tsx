"use client";

import { Button, ErrorState, formatMoney, Icon, PageHeader, Panel, SectionHeading, Skeleton, useAccessToken, useVendorQuery } from "@/components/portal";
import type { RevenueReport } from "@/types/vendor";

export default function VendorRevenuePage() {
  const token = useAccessToken();
  const report = useVendorQuery<RevenueReport>("/revenue", token);
  return <>
    <PageHeader eyebrow="SETTLEMENT VIEW" title="Revenue" description="Gross receipts and your settlement estimate use verified booking payments and completed refunds." action={<Button variant="secondary" onClick={report.reload}><Icon name="refresh"/>Refresh</Button>}/>
    {report.loading ? <><Panel className="panel-pad"><Skeleton rows={4}/></Panel><div className="revenue-stat-grid">{[1,2,3].map((item) => <Panel key={item} className="panel-pad"><Skeleton rows={2}/></Panel>)}</div></> : report.error ? <Panel><ErrorState message={report.error} onRetry={report.reload}/></Panel> : report.data && <>
      <div className="revenue-hero"><div><span>Today · captured payments</span><strong>{formatMoney(report.data.today_gross)}</strong><small>Based on server-confirmed Razorpay status</small></div><span className="metric-icon"><Icon name="chart" size={24}/></span></div>
      <div className="revenue-stat-grid"><Panel className="revenue-stat"><span>This week · captured</span><strong>{formatMoney(report.data.week_gross)}</strong></Panel><Panel className="revenue-stat"><span>This month · captured</span><strong>{formatMoney(report.data.month_gross)}</strong></Panel><Panel className="revenue-stat"><span>All-time bookings</span><strong>{report.data.total_bookings}</strong></Panel></div>
      <Panel className="panel-pad"><SectionHeading title="Settlement estimate" detail={`${report.data.commission_rate_bps / 100}% accounting policy on new verified charging captures · completed refunds reduce the estimate`}/><div className="revenue-stat-grid"><Panel className="revenue-stat"><span>All-time gross</span><strong>{formatMoney(report.data.all_time_gross)}</strong></Panel><Panel className="revenue-stat"><span>Completed refunds</span><strong>{formatMoney(report.data.completed_refunds)}</strong></Panel><Panel className="revenue-stat"><span>Calculated commission</span><strong>{formatMoney(report.data.platform_fee)}</strong></Panel><Panel className="revenue-stat"><span>Estimated vendor balance · unpaid</span><strong>{formatMoney(report.data.estimated_payout)}</strong></Panel></div>
        <div className="warning-copy" style={{ marginTop: 17 }}>The 5% commission is an accounting calculation; customer payments are not split to vendors. VoltStop does not initiate or mark vendor payouts as transferred.</div>
      </Panel>
      <Panel className="panel-pad"><SectionHeading title="Booking outcomes" detail="Derived from your vendor-scoped booking records"/><div className="mini-stats"><div className="mini-stat"><strong>{report.data.completed_bookings}</strong><span>COMPLETED</span></div><div className="mini-stat"><strong>{report.data.cancelled_bookings}</strong><span>CANCELLED</span></div><div className="mini-stat"><strong>{report.data.refunded_payments}</strong><span>REFUNDED PAYMENTS</span></div></div>
      </Panel>
    </>}
  </>;
}
