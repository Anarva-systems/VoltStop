"use client";

import { AdminCard, AdminLoad, AdminPage, AdminTable, StateBadge, formatAdminDate, formatAdminMoney, useAdminQuery, useAdminToken } from "@/components/admin-ui";

type Order = { id: string; vendor_id: string; restaurant_name: string; status: string; total_inr: string; payment_status: string | null; webhook_verified: boolean; created_at: string; items: { name: string; quantity: number; line_total_inr: string }[] };

export default function AdminRestaurantOrdersPage() {
  const token = useAdminToken();
  const orders = useAdminQuery<Order[]>("/restaurant-orders", token);
  return <><AdminPage title="Restaurant order monitor" description="Read-only view of persisted restaurant orders and payment states. Fulfilment requires a verified payment webhook."/>
    <AdminCard><AdminLoad loading={orders.loading} error={orders.error} data={orders.data} retry={orders.reload} empty={Boolean(orders.data && orders.data.length === 0)} emptyTitle="No restaurant orders have been recorded">{(rows) => <AdminTable headers={["Order","Restaurant","Items","Total","Payment","Fulfilment","Created"]}>{rows.map((order) => <tr key={order.id}>
      <td className="primary-cell">{order.id.slice(0,12)}…</td><td>{order.restaurant_name}<div className="table-secondary">{order.vendor_id}</div></td>
      <td>{order.items.map((item) => `${item.quantity} × ${item.name}`).join(" · ")}</td><td>{formatAdminMoney(order.total_inr)}</td>
      <td><StateBadge value={order.webhook_verified ? order.payment_status || "verified" : "unverified"}/></td><td><StateBadge value={order.status}/></td><td>{formatAdminDate(order.created_at,true)}</td>
    </tr>)}</AdminTable>}</AdminLoad></AdminCard>
  </>;
}
