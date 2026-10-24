"use client";

import Link from "next/link";
import { useState } from "react";
import { adminPost } from "@/services/admin-api";
import { toast, Button } from "@/components/portal";
import { AdminCard, AdminLoad, AdminPage, AdminTable, FilterInput, FilterSelect, StateBadge, formatAdminDate, formatAdminMoney, useAdminQuery, useAdminToken } from "@/components/admin-ui";

type Dispute={id:string;booking_id:string;reason:string;description:string;status:string;created_at:string;updated_at:string;amount_inr:string;customer_name:string;vendor_name:string};
type Page={items:Dispute[];total:number};
type Me={permissions:string[]};

export default function DisputesPage(){
  const token=useAdminToken();
  const me=useAdminQuery<Me>("/me",token);const canManage=Boolean(me.data?.permissions.includes("disputes:manage"));
  const[status,setStatus]=useState("");const[vendorId,setVendorId]=useState("");const[customerId,setCustomerId]=useState("");
  const[dateFrom,setDateFrom]=useState("");const[dateTo,setDateTo]=useState("");const[minAmount,setMinAmount]=useState("");const[maxAmount,setMaxAmount]=useState("");const[reasonFilter,setReasonFilter]=useState("");
  const[create,setCreate]=useState(false);const[booking,setBooking]=useState("");const[reason,setReason]=useState("");const[description,setDescription]=useState("");const[busy,setBusy]=useState(false);
  const params=new URLSearchParams({limit:"100"});
  if(status)params.set("status",status);if(vendorId)params.set("vendor_id",vendorId.trim());if(customerId)params.set("customer_id",customerId.trim());
  if(dateFrom)params.set("date_from",new Date(`${dateFrom}T00:00:00Z`).toISOString());if(dateTo)params.set("date_to",new Date(`${dateTo}T23:59:59Z`).toISOString());
  if(minAmount)params.set("minimum_amount",minAmount);if(maxAmount)params.set("maximum_amount",maxAmount);if(reasonFilter)params.set("reason",reasonFilter);
  const q=useAdminQuery<Page>(`/disputes?${params}`,token);
  async function submit(event:React.FormEvent){event.preventDefault();if(!token)return;setBusy(true);try{await adminPost("/disputes",token,{booking_id:booking,reason,description},{"Idempotency-Key":crypto.randomUUID()});toast("Dispute opened");setCreate(false);setBooking("");setReason("");setDescription("");q.reload();}catch(e){toast(e instanceof Error?e.message:"Could not open dispute");}finally{setBusy(false);}}

  return <>
    <AdminPage title="Complaints & disputes" description="Investigate customer booking complaints, record an immutable event timeline, and route refunds through the audited finance workflow." action={canManage?<Button onClick={()=>setCreate(true)}>Open dispute</Button>:undefined}/>
    <AdminCard>
      <div className="admin-toolbar" style={{flexWrap:"wrap"}}>
        <FilterSelect aria-label="All statuses" value={status} onChange={(e)=>setStatus(e.target.value)}><option value="">All statuses</option>{["open","investigating","awaiting_customer","awaiting_vendor","resolved","closed"].map((x)=><option key={x}>{x}</option>)}</FilterSelect>
        <FilterInput placeholder="Vendor ID" value={vendorId} onChange={(e)=>setVendorId(e.target.value)}/><FilterInput placeholder="Customer ID" value={customerId} onChange={(e)=>setCustomerId(e.target.value)}/>
        <label className="admin-filter-label">From <input className="admin-filter" type="date" value={dateFrom} onChange={(e)=>setDateFrom(e.target.value)}/></label><label className="admin-filter-label">To <input className="admin-filter" type="date" value={dateTo} onChange={(e)=>setDateTo(e.target.value)}/></label>
        <FilterInput type="number" min="0" placeholder="Min amount" value={minAmount} onChange={(e)=>setMinAmount(e.target.value)}/><FilterInput type="number" min="0" placeholder="Max amount" value={maxAmount} onChange={(e)=>setMaxAmount(e.target.value)}/><FilterInput placeholder="Reason contains…" value={reasonFilter} onChange={(e)=>setReasonFilter(e.target.value)}/>
      </div>
      <AdminLoad loading={q.loading} error={q.error} data={q.data} retry={q.reload} empty={Boolean(q.data&&!q.data.items.length)} emptyTitle="No disputes match these filters">{(d)=><AdminTable headers={["Dispute ID","Booking","Customer","Vendor","Amount","Reason","Status","Created","Updated"]}>{d.items.map((r)=><tr key={r.id}><td className="primary-cell"><Link href={`/admin/disputes/${r.id}`}>{r.id.slice(0,12)}…</Link></td><td>{r.booking_id.slice(0,12)}…</td><td>{r.customer_name}</td><td>{r.vendor_name}</td><td>{formatAdminMoney(r.amount_inr)}</td><td>{r.reason}</td><td><StateBadge value={r.status}/></td><td>{formatAdminDate(r.created_at,true)}</td><td>{formatAdminDate(r.updated_at,true)}</td></tr>)}</AdminTable>}</AdminLoad>
    </AdminCard>
    {create&&<div className="admin-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setCreate(false); }}><form className="admin-modal" onSubmit={submit} role="dialog" aria-modal="true"><div className="admin-modal-head"><h2>Open a dispute</h2><button type="button" className="admin-modal-close" aria-label="Close dialog" onClick={()=>setCreate(false)}>×</button></div><p>Party identities and amount are derived from the booking by the server.</p><label className="admin-reason">Booking ID<input className="admin-filter" required value={booking} onChange={(e)=>setBooking(e.target.value)}/></label><label className="admin-reason">Reason<input className="admin-filter" required minLength={3} value={reason} onChange={(e)=>setReason(e.target.value)}/></label><label className="admin-reason">Description<textarea className="admin-filter" minLength={8} required value={description} onChange={(e)=>setDescription(e.target.value)}/></label><div className="admin-modal-actions"><Button variant="secondary" type="button" disabled={busy} onClick={()=>setCreate(false)}>Cancel</Button><Button type="submit" disabled={busy}>{busy?"Opening…":"Create dispute"}</Button></div></form></div>}
  </>;
}
