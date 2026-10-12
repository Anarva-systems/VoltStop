"use client";

import { useEffect, useState } from "react";
import { adminPost } from "@/services/admin-api";
import { toast } from "@/components/portal";
import { AdminButton, AdminCard, AdminLoad, AdminPage, AdminTable, FilterSelect, StateBadge, formatAdminDate, formatAdminMoney, useAdminQuery, useAdminToken } from "@/components/admin-ui";

type Refund={id:string;booking_id:string;payment_id:string;amount_inr:string;reason:string;status:string;razorpay_refund_id:string|null;provider_status:string|null;provider_error:string|null;created_at:string;vendor_name:string;customer_name:string;razorpay_payment_id:string};
type Results={items:Refund[];total:number};
type Eligibility={booking_id:string;booking_status:string;amount_inr:string;payment_status:string;webhook_verified:boolean;vendor_name:string;customer_name:string;remaining_refundable_amount:string;eligible:boolean;active_refund:boolean};
type AdminMe={permissions:string[]};
type Decision={refund:Refund;action:"approve"|"reject"};

export default function RefundsPage(){
  const token=useAdminToken();
  const [status,setStatus]=useState("");
  const [open,setOpen]=useState(false);
  const [decision,setDecision]=useState<Decision|null>(null);
  const [booking,setBooking]=useState("");
  const [amount,setAmount]=useState("");
  const [reason,setReason]=useState("");
  const [phrase,setPhrase]=useState("");
  const [busy,setBusy]=useState(false);
  useEffect(()=>{const value=new URLSearchParams(window.location.search).get("booking_id");if(value){setBooking(value);setOpen(true);}},[]);
  const validBooking=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(booking.trim());
  const eligibility=useAdminQuery<Eligibility>(validBooking?`/refunds/eligibility?booking_id=${booking.trim()}`:"",token);
  const me=useAdminQuery<AdminMe>("/me",token);
  const canRequest=Boolean(me.data?.permissions.includes("refunds:create"));
  const canApprove=Boolean(me.data?.permissions.includes("refunds:approve"));
  const params=new URLSearchParams({limit:"100"});if(status)params.set("status",status);
  const q=useAdminQuery<Results>(`/refunds?${params}`,token);
  const exceeds=Boolean(amount&&eligibility.data&&Number(amount)>Number(eligibility.data.remaining_refundable_amount));

  async function requestRefund(event:React.FormEvent<HTMLFormElement>){
    event.preventDefault();
    if(!token||!eligibility.data?.eligible||exceeds)return;
    setBusy(true);
    try{
      await adminPost<Refund>("/refunds",token,{booking_id:booking.trim(),...(amount?{amount_inr:amount}:{}),reason},{"Idempotency-Key":crypto.randomUUID()});
      toast("Refund request submitted for finance approval");
      setOpen(false);setBooking("");setAmount("");setReason("");q.reload();
    }catch(error){toast(error instanceof Error?error.message:"Refund request could not be submitted");}
    finally{setBusy(false);}
  }

  async function decideRefund(event:React.FormEvent<HTMLFormElement>){
    event.preventDefault();
    if(!token||!decision||(decision.action==="approve"&&phrase!=="REFUND"))return;
    setBusy(true);
    try{
      const action=decision.action;
      await adminPost<Refund>(`/refunds/${decision.refund.id}/${action}`,token,{reason});
      toast(action==="approve"?"Refund approved and submitted to Razorpay":"Refund request rejected");
      setDecision(null);setReason("");setPhrase("");q.reload();
    }catch(error){toast(error instanceof Error?error.message:"Refund decision could not be completed");q.reload();}
    finally{setBusy(false);}
  }

  return <>
    <AdminPage title="Refunds" description="Refund requests are recorded first. Finance approval is separately audited before the backend submits a verified amount to Razorpay." action={canRequest?<AdminButton onClick={()=>setOpen(true)}>Request refund</AdminButton>:undefined}/>
    <AdminCard>
      <div className="admin-toolbar"><FilterSelect value={status} onChange={(event)=>setStatus(event.target.value)}><option value="">All refund states</option>{["requested","approved","processing","completed","failed","rejected"].map((item)=><option key={item}>{item}</option>)}</FilterSelect></div>
      <AdminLoad loading={q.loading} error={q.error} data={q.data} retry={q.reload} empty={Boolean(q.data&&!q.data.items.length)} emptyTitle="No refunds recorded">{(data)=><AdminTable headers={["Refund","Booking","Vendor","Customer","Amount","State","Provider","Created","Reason","Action"]}>{data.items.map((row)=><tr key={row.id}>
        <td className="primary-cell">{row.razorpay_refund_id??row.id.slice(0,12)}</td><td>{row.booking_id.slice(0,12)}…</td><td>{row.vendor_name}</td><td>{row.customer_name}</td><td>{formatAdminMoney(row.amount_inr)}</td><td><StateBadge value={row.status}/></td><td>{row.provider_status??"Awaiting confirmation"}{row.provider_error&&<small style={{display:"block",color:"#f6c453"}}>Needs reconciliation</small>}</td><td>{formatAdminDate(row.created_at,true)}</td><td>{row.reason}</td>
        <td>{row.status==="requested"&&canApprove?<div className="admin-toolbar"><AdminButton onClick={()=>{setDecision({refund:row,action:"approve"});setReason("");}}>Approve &amp; issue</AdminButton><AdminButton variant="danger" onClick={()=>{setDecision({refund:row,action:"reject"});setReason("");}}>Reject</AdminButton></div>:"—"}</td>
      </tr>)}</AdminTable>}</AdminLoad>
    </AdminCard>

    {open&&<div className="admin-modal-backdrop"><form className="admin-modal" onSubmit={requestRefund} role="dialog" aria-modal="true"><div className="admin-modal-head"><h2>Request a refund</h2><button type="button" className="admin-modal-close" onClick={()=>setOpen(false)}>×</button></div><p>This records a request for finance approval. The backend checks captured payment status, webhook verification, and the remaining refundable amount.</p>
      <label className="admin-reason">Booking ID<input className="admin-filter" required value={booking} onChange={(event)=>{setBooking(event.target.value);setAmount("");}} placeholder="UUID"/></label>
      {validBooking&&(eligibility.loading?<div className="admin-callout">Checking verified payment and remaining refundable amount…</div>:eligibility.error?<div className="admin-note">{eligibility.error}</div>:eligibility.data&&<div className="admin-callout">{eligibility.data.eligible?<>Booking {eligibility.data.booking_id.slice(0,12)}… · {eligibility.data.customer_name} · {eligibility.data.vendor_name} · captured {formatAdminMoney(eligibility.data.amount_inr)} · remaining {formatAdminMoney(eligibility.data.remaining_refundable_amount)}</>:<>Refund unavailable · payment state {eligibility.data.payment_status}{eligibility.data.active_refund?" · another refund is pending or processing":""}</>}</div>)}
      <label className="admin-reason">Refund amount in INR <span>(leave blank for the server calculated remaining amount)</span><input className="admin-filter" type="number" min="0.01" step="0.01" value={amount} onChange={(event)=>setAmount(event.target.value)} placeholder="Full remaining amount"/></label>
      {eligibility.data?.eligible&&<div className={exceeds?"admin-note":"admin-callout"}>Requesting {formatAdminMoney(amount||eligibility.data.remaining_refundable_amount)} to {eligibility.data.customer_name} for booking {eligibility.data.booking_id.slice(0,12)}… at {eligibility.data.vendor_name}.{exceeds?" Amount exceeds the server confirmed remaining amount.":" This request still requires finance approval."}</div>}
      <label className="admin-reason">Request reason<textarea className="admin-filter" required minLength={8} maxLength={1000} value={reason} onChange={(event)=>setReason(event.target.value)} placeholder="Explain why this refund is requested"/></label>
      <div className="admin-modal-actions"><button className="button button-secondary" type="button" disabled={busy} onClick={()=>setOpen(false)}>Cancel</button><AdminButton type="submit" busy={busy} disabled={!eligibility.data?.eligible||exceeds}>Submit request</AdminButton></div>
    </form></div>}

    {decision&&<div className="admin-modal-backdrop"><form className="admin-modal" onSubmit={decideRefund} role="dialog" aria-modal="true"><div className="admin-modal-head"><h2>{decision.action==="approve"?"Approve and issue refund":"Reject refund request"}</h2><button type="button" className="admin-modal-close" onClick={()=>setDecision(null)}>×</button></div>
      <p>{decision.action==="approve"?"This approval is recorded before the server submits the verified refund to Razorpay. Provider responses may remain pending and are reconciled by webhook.":"This rejects the pending request. No payment provider call will be made."}</p>
      <div className="admin-callout">{formatAdminMoney(decision.refund.amount_inr)} · booking {decision.refund.booking_id.slice(0,12)}… · {decision.refund.customer_name} · {decision.refund.vendor_name}<br/>Original request: {decision.refund.reason}</div>
      <label className="admin-reason">{decision.action==="approve"?"Approval reason":"Rejection reason"}<textarea className="admin-filter" required minLength={8} maxLength={1000} value={reason} onChange={(event)=>setReason(event.target.value)} placeholder="Add the finance decision reason"/></label>
      {decision.action==="approve"&&<label className="admin-reason">Type REFUND to confirm this external financial operation<input className="admin-filter" required value={phrase} onChange={(event)=>setPhrase(event.target.value)} placeholder="REFUND"/></label>}
      <div className="admin-modal-actions"><button className="button button-secondary" type="button" disabled={busy} onClick={()=>setDecision(null)}>Cancel</button><AdminButton variant="danger" type="submit" busy={busy} disabled={decision.action==="approve"&&phrase!=="REFUND"}>{decision.action==="approve"?"Approve &amp; issue":"Reject request"}</AdminButton></div>
    </form></div>}
  </>;
}
