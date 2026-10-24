"use client";

import { FormEvent, useState } from "react";
import { apiPost, apiPatch, vendorApi } from "@/services/api";
import { Button, EmptyState, ErrorState, formatMoney, PageHeader, Panel, SectionHeading, Skeleton, StatePill, toast, useAccessToken, useVendorQuery } from "@/components/portal";

type Item = { id: string; name: string; description: string | null; price_inr: number; is_available: boolean; options: { name: string; required: boolean; choices: { name: string; price_delta_inr: number }[] }[] };
type Category = { id: string; name: string; sort_order: number; is_active: boolean; items: Item[] };
type Menu = { categories: Category[] };
type Order = { id: string; restaurant_name: string; customer_name: string | null; customer_phone: string | null; status: string; total_inr: number; payment_status: string | null; webhook_verified: boolean; created_at?: string; items: { name: string; quantity: number; line_total_inr: number }[] };
type Sales = { today_gross_inr: number; week_gross_inr: number; month_gross_inr: number; total_orders: number; paid_orders: number };

export function RestaurantManagement() {
  const token = useAccessToken();
  const menu = useVendorQuery<Menu>("/restaurants/menu", token);
  const orders = useVendorQuery<Order[]>("/restaurants/orders", token);
  const sales = useVendorQuery<Sales>("/restaurants/financials", token);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Item | null>(null);
  const [editingCategoryId, setEditingCategoryId] = useState("");

  async function addCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!token) return;
    const form = new FormData(event.currentTarget); setBusy(true);
    try { await apiPost("/restaurants/categories", token, { name: String(form.get("name")).trim(), sort_order: Number(form.get("sort_order") || 0) }); event.currentTarget.reset(); menu.reload(); toast("Menu category added"); }
    catch (error) { toast(error instanceof Error ? error.message : "Category could not be saved"); }
    finally { setBusy(false); }
  }

  async function addItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!token) return;
    const form = new FormData(event.currentTarget); let options: Item["options"] = [];
    const raw = String(form.get("options") || "").trim();
    try { if (raw) { const parsed = JSON.parse(raw) as unknown; if (!Array.isArray(parsed)) throw new Error("Options must be a JSON array"); options = parsed as Item["options"]; } }
    catch (error) { toast(error instanceof Error ? error.message : "Options JSON is invalid"); return; }
    setBusy(true);
    const value = { category_id: String(form.get("category_id")), name: String(form.get("name")).trim(), description: String(form.get("description")).trim() || null, price_inr: Number(form.get("price_inr")), is_available: editing?.is_available ?? true, options };
    try { if (editing) await apiPatch(`/restaurants/items/${editing.id}`, token, value); else await apiPost("/restaurants/items", token, value); event.currentTarget.reset(); setEditing(null); setEditingCategoryId(""); menu.reload(); toast(editing ? "Menu item updated" : "Menu item added"); }
    catch (error) { toast(error instanceof Error ? error.message : "Menu item could not be saved"); }
    finally { setBusy(false); }
  }

  async function toggleItem(item: Item) {
    if (!token) return; setBusy(true);
    try { await apiPatch(`/restaurants/items/${item.id}`, token, { is_available: !item.is_available }); menu.reload(); toast(item.is_available ? "Menu item paused" : "Menu item available"); }
    catch (error) { toast(error instanceof Error ? error.message : "Menu item could not be updated"); }
    finally { setBusy(false); }
  }

  async function transition(order: Order, status: string) {
    if (!token) return; setBusy(true);
    try { await vendorApi(`/restaurants/orders/${order.id}/status`, token, { method: "POST", body: JSON.stringify({ status }) }); orders.reload(); toast(`Order ${status}`); }
    catch (error) { toast(error instanceof Error ? error.message : "Order status could not be updated"); }
    finally { setBusy(false); }
  }

  const categories = menu.data?.categories ?? [];
  return <>
    <PageHeader eyebrow="RESTAURANT" title="Menu & orders" description="Maintain published menu items and advance pickup orders only after the API verifies payment." />
    <SectionHeading title="Menu categories" detail="Categories and items shown to authenticated VoltStop customers." />
    {menu.loading ? <Panel><Skeleton rows={4}/></Panel> : menu.error ? <Panel><ErrorState message={menu.error} onRetry={menu.reload}/></Panel> : <>
      <Panel className="panel-pad"><form onSubmit={addCategory} className="form-grid" style={{gridTemplateColumns:"minmax(180px,1fr) 120px auto",alignItems:"end"}}>
        <label className="label-control">New category<input name="name" required minLength={2} maxLength={80} className="input-control" placeholder="Breakfast"/></label>
        <label className="label-control">Order<input name="sort_order" type="number" min="0" defaultValue="0" className="input-control"/></label><Button disabled={busy}>Add category</Button>
      </form></Panel>
      {!categories.length ? <Panel style={{marginTop:16}}><EmptyState title="No menu categories" description="Add a category before publishing food items."/></Panel> : categories.map((category) => <Panel key={category.id} className="panel-pad" style={{marginTop:16}}>
        <SectionHeading title={category.name} detail={`${category.items.length} menu item${category.items.length === 1 ? "" : "s"}`}/>
        {!category.items.length ? <p className="label-note">No items in this category yet.</p> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Item</th><th>Price</th><th>Availability</th><th/></tr></thead><tbody>{category.items.map((item) => <tr key={item.id}><td><strong>{item.name}</strong><div className="table-secondary">{item.description || "No description"}{item.options.length ? ` · ${item.options.length} option groups` : ""}</div></td><td>{formatMoney(item.price_inr)}</td><td><StatePill value={item.is_available ? "available" : "closed"}/></td><td><div className="table-actions"><button className="action-link" onClick={() => { setEditing(item); setEditingCategoryId(category.id); }}>Edit</button><Button variant="secondary" disabled={busy} onClick={() => toggleItem(item)}>{item.is_available ? "Pause" : "Publish"}</Button></div></td></tr>)}</tbody></table></div>}
      </Panel>)}
      {categories.length > 0 && <Panel className="panel-pad" style={{marginTop:16}}><SectionHeading title={editing ? `Edit ${editing.name}` : "Add menu item"} detail="Prices and options are validated again by the API at checkout."/><form key={editing?.id ?? "new-item"} onSubmit={addItem} className="form-grid">
        <label className="label-control">Category<select name="category_id" className="select-control" required defaultValue={editingCategoryId || categories.find((item) => item.is_active)?.id}>{categories.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label className="label-control">Item name<input name="name" required minLength={2} maxLength={120} className="input-control" defaultValue={editing?.name}/></label>
        <label className="label-control">Price · INR<input name="price_inr" required type="number" min="0.01" step="0.01" className="input-control" defaultValue={editing?.price_inr}/></label>
        <label className="label-control form-span-2">Description<input name="description" maxLength={1000} className="input-control" defaultValue={editing?.description ?? ""}/></label>
        <label className="label-control form-span-2">Options · JSON array (optional)<textarea name="options" className="textarea-control" defaultValue={editing ? JSON.stringify(editing.options) : ""} placeholder={'[{"name":"Size","required":true,"choices":[{"name":"Regular","price_delta_inr":0},{"name":"Large","price_delta_inr":35}]}]'}/></label>
        <div className="form-actions"><Button disabled={busy}>{editing ? "Save changes" : "Publish item"}</Button>{editing && <Button type="button" variant="secondary" onClick={() => { setEditing(null); setEditingCategoryId(""); }}>Cancel edit</Button>}</div>
      </form></Panel>}
    </>}
    <SectionHeading title="Incoming orders" detail="Only captured payments with a verified webhook can be accepted or fulfilled." />
    {sales.loading ? <Panel><Skeleton rows={2}/></Panel> : sales.error ? <Panel><ErrorState message={sales.error} onRetry={sales.reload}/></Panel> : sales.data && <div className="service-grid" style={{marginBottom:18}}>{[["Today verified gross",sales.data.today_gross_inr],["This week",sales.data.week_gross_inr],["This month",sales.data.month_gross_inr],["Paid orders",`${sales.data.paid_orders} / ${sales.data.total_orders}`]].map(([label,value]) => <Panel key={String(label)} className="panel-pad"><span className="label-note">{label}</span><h2>{typeof value === "number" ? formatMoney(value) : value}</h2></Panel>)}</div>}
    {orders.loading ? <Panel><Skeleton rows={5}/></Panel> : orders.error ? <Panel><ErrorState message={orders.error} onRetry={orders.reload}/></Panel> : !orders.data?.length ? <Panel><EmptyState title="No orders yet" description="Customer pickup orders will appear here after verified checkout."/></Panel> : <div className="service-grid">{orders.data.map((order) => {
      const next = ({placed:"accepted",accepted:"preparing",preparing:"ready",ready:"completed"} as Record<string,string>)[order.status];
      return <Panel key={order.id} className="panel-pad"><div className="table-actions"><strong>Order {order.id.slice(0,10)}</strong><StatePill value={order.status}/></div><p>{order.customer_name || "Customer"}{order.customer_phone ? ` · ${order.customer_phone}` : ""}</p><p>{order.items.map((item) => `${item.quantity} × ${item.name}`).join(" · ")}</p><div className="table-actions"><span>{formatMoney(order.total_inr)}</span><StatePill value={order.webhook_verified ? order.payment_status || "verified" : "unverified"}/></div>{next && <Button disabled={busy || !order.webhook_verified} onClick={() => transition(order,next)} style={{marginTop:14}}>Mark {next}</Button>}</Panel>;
    })}</div>}
  </>;
}
