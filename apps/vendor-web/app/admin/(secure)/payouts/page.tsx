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

type Payout = {
  vendor_id: string;
  name: string;
  gross_revenue: string;
  completed_refunds?: string;
  refunds?: string;
  platform_fee: string | null;
  calculated_payout: string | null;
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
      title="Vendor settlement estimates"
      description="Balances are accounting estimates from verified charging payments and completed refunds. The 5% policy is not split from customer payments and this page does not send money."
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
          "Gross revenue",
          "Completed refunds",
          "Calculated commission",
          "Estimated vendor balance · unpaid",
          "Settlement",
        ]}>
          {data.items.map((row) => <tr key={row.vendor_id}>
            <td className="primary-cell">{row.name}</td>
            <td>{formatAdminMoney(row.gross_revenue)}</td>
            <td>{formatAdminMoney(row.refunds ?? row.completed_refunds)}</td>
            <td>{formatAdminMoney(row.platform_fee)}</td>
            <td>{formatAdminMoney(row.calculated_payout)}</td>
            <td><StateBadge value={row.payout_status} /></td>
          </tr>)}
        </AdminTable>}
      </AdminLoad>
    </AdminCard>
  </>;
}
