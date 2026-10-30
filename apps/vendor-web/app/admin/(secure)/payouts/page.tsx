"use client";

import {
  AdminCard,
  AdminLoad,
  AdminPage,
  AdminTable,
  StateBadge,
  formatAdminMoney,
  useAdminQuery,
  useAdminToken,
} from "@/components/admin-ui";
import { TransferLedger } from "@/components/admin-payout";

type Payout = {
  vendor_id: string;
  name: string;
  payouts_enabled: boolean;
  gross_revenue: string;
  completed_refunds?: string;
  refunds?: string;
  platform_fee: string | null;
  calculated_payout: string | null;
  routed_inr: string;
  planned_inr: string;
  failed_transfers: number;
  payout_status: string;
};

type Results = {
  items: Payout[];
  total: number;
  commission_rate_bps: number;
  notice: string;
};

export default function PayoutsPage() {
  const token = useAdminToken();
  const query = useAdminQuery<Results>("/payouts?limit=100", token);

  return <>
    <AdminPage
      title="Vendor settlement"
      description="Upper balances are accounting estimates from verified payments and completed refunds. The ledger below shows what Razorpay Route has actually been told to move, per transfer."
    />
    <AdminCard>
      {query.data && <div className="admin-note" style={{ marginBottom: 13 }}>{query.data.notice}</div>}
      <AdminLoad
        loading={query.loading}
        error={query.error}
        data={query.data}
        retry={query.reload}
        empty={Boolean(query.data && !query.data.items.length)}
        emptyTitle="No vendor balances yet"
      >
        {(data) => <AdminTable headers={[
          "Vendor",
          "Routing",
          "Gross revenue",
          "Completed refunds",
          "Calculated commission",
          "Estimated vendor balance · unpaid",
          "Routed",
          "Planned",
          "Failed",
          "Settlement",
        ]}>
          {data.items.map((row) => <tr key={row.vendor_id}>
            <td className="primary-cell">{row.name}</td>
            <td><StateBadge value={row.payouts_enabled ? "enabled" : "disabled"} /></td>
            <td>{formatAdminMoney(row.gross_revenue)}</td>
            <td>{formatAdminMoney(row.refunds ?? row.completed_refunds)}</td>
            <td>{formatAdminMoney(row.platform_fee)}</td>
            <td>{formatAdminMoney(row.calculated_payout)}</td>
            <td>{formatAdminMoney(row.routed_inr)}</td>
            <td>{formatAdminMoney(row.planned_inr)}</td>
            <td>{row.failed_transfers}</td>
            <td><StateBadge value={row.payout_status} /></td>
          </tr>)}
        </AdminTable>}
      </AdminLoad>
    </AdminCard>
    <AdminCard title="Transfer ledger" subtitle="Every transfer across charging, hotel and restaurant bookings, newest first. Planned rows are instructions, not confirmed money.">
      <TransferLedger path="/payout-transfers?limit=50" />
    </AdminCard>
  </>;
}
