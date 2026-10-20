"use client";

import { useState } from "react";
import { vendorApi } from "@/services/api";
import { Button, EmptyState, ErrorState, formatDate, formatMoney, PageHeader, Panel, Skeleton, StatePill, toast, useAccessToken, useVendorQuery } from "@/components/portal";

type Dispute={id:string;booking_id:string;customer_id:string;amount_inr:string;reason:string;description:string;status:string;created_at:string;updated_at:string};
type Page={items:Dispute[];total:number};

export default function VendorDisputesPage(){
  const token=useAccessToken();const q=useVendorQuery<Page>("/disputes?limit=100",token);const[message,setMessage]=useState<Record<string,string>>({});const[busy,setBusy]=useState("");
  async function respond(id:string){if(!token||!message[id]?.trim())return;setBusy(id);try{await vendorApi(`/disputes/${id}/messages`,token,{method:"POST",headers:{"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({message:message[id]})});toast("Your response was added to the booking issue");setMessage({...message,[id]:""});q.reload();}catch(error){toast(error instanceof Error?error.message:"Could not send response");}finally{setBusy("");}}
  if(q.loading)return <><PageHeader eyebrow="CUSTOMER SUPPORT" title="Booking issues" description="Review and respond to customer-reported issues about your bookings."/><Panel className="panel-pad"><Skeleton rows={6}/></Panel></>;
  if(q.error)return <><PageHeader eyebrow="CUSTOMER SUPPORT" title="Booking issues"/><Panel><ErrorState message={q.error} onRetry={q.reload}/></Panel></>;
  return <><PageHeader eyebrow="CUSTOMER SUPPORT" title="Booking issues" description="Review customer-reported issues involving your bookings. VoltStop support handles financial decisions and final resolution."/>
    {!q.data?.items.length?<Panel><EmptyState title="No booking issues" description="If a customer raises an issue about one of your bookings, it will appear here."/></Panel>:<div className="card-grid">{q.data.items.map((item)=><Panel key={item.id} className="panel-pad"><div className="section-heading"><div><p className="eyebrow">BOOKING ISSUE {item.id.slice(0,12)}…</p><h2>{item.reason}</h2></div><StatePill value={item.status}/></div><p>{item.description}</p><div className="detail-grid"><div><small>Booking</small><strong>{item.booking_id}</strong></div><div><small>Amount</small><strong>{formatMoney(item.amount_inr)}</strong></div><div><small>Opened</small><strong>{formatDate(item.created_at)}</strong></div></div>
      {!['resolved','closed'].includes(item.status)&&<div className="form-stack" style={{marginTop:16}}><label className="label-control">Your response<textarea className="textarea-control" minLength={4} maxLength={4000} value={message[item.id]??""} onChange={(event)=>setMessage({...message,[item.id]:event.target.value})} placeholder="Share the details VoltStop support should consider"/></label><Button disabled={busy===item.id||!message[item.id]?.trim()} onClick={()=>void respond(item.id)}>{busy===item.id?"Sending…":"Send response"}</Button></div>}
    </Panel>)}</div>}</>;
}
