"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { adminPost } from "@/services/admin-api";
import { toast, Button } from "@/components/portal";
import { AdminCard, AdminLoad, AdminPage, FilterSelect, StateBadge, formatAdminDate, formatAdminMoney, useAdminQuery, useAdminToken } from "@/components/admin-ui";

type Event={event_type:string;actor_type:string;message:string|null;metadata:Record<string,unknown>;created_at:string};
type LinkedRefund={id:string;amount_inr:string;status:string;reason:string;created_at:string};
type Detail={id:string;booking_id:string;reason:string;description:string;status:string;evidence:unknown[];resolution:string|null;created_at:string;updated_at:string;resolved_at:string|null;amount_inr:string;booking_status:string;payment_status:string;payment_amount:string|null;customer_id:string;customer_name:string;customer_phone:string;vendor_id:string;vendor_name:string;vendor_phone:string;timeline:Event[];linked_refunds:LinkedRefund[]};
type Eligibility={amount_inr:string;completed_refunds:string;previously_refunded_amount:string;remaining_refundable_amount:string;eligible:boolean;active_refund:boolean;payment_status:string};
type Me={permissions:string[]};

export default function DisputeDetailPage(){
  const{disputeId}=useParams<{disputeId:string}>();const token=useAdminToken();const q=useAdminQuery<Detail>(`/disputes/${disputeId}`,token);
  const me=useAdminQuery<Me>("/me",token);const[action,setAction]=useState("investigate");const[message,setMessage]=useState("");const[busy,setBusy]=useState(false);const[approvalReason,setApprovalReason]=useState("");const[approvalPhrase,setApprovalPhrase]=useState("");
  const canRequestRefund=Boolean(me.data?.permissions.includes("refunds:create"));
  const canApproveRefund=Boolean(me.data?.permissions.includes("refunds:approve"));
  const canManageDisputes=Boolean(me.data?.permissions.includes("disputes:manage"));
  const eligibility=useAdminQuery<Eligibility>(canRequestRefund&&q.data?`/refunds/eligibility?booking_id=${q.data.booking_id}`:"",token);
  const[refundAmount,setRefundAmount]=useState("");const[refundReason,setRefundReason]=useState("");
  async function submit(event:React.FormEvent){event.preventDefault();if(!token)return;setBusy(true);try{await adminPost(`/disputes/${disputeId}/action`,token,{action,message},{"Idempotency-Key":crypto.randomUUID()});toast("Dispute action recorded");setMessage("");q.reload();}catch(e){toast(e instanceof Error?e.message:"Dispute action failed");}finally{setBusy(false);}}
  async function requestRefund(event:React.FormEvent){event.preventDefault();if(!token||!q.data||!eligibility.data?.eligible)return;setBusy(true);try{await adminPost(`/disputes/${disputeId}/refund-request`,token,{amount_inr:refundAmount||eligibility.data.remaining_refundable_amount,reason:refundReason},{"Idempotency-Key":crypto.randomUUID()});toast("Refund request recorded; Finance approval is still required");setRefundAmount("");setRefundReason("");eligibility.reload();q.reload();}catch(e){toast(e instanceof Error?e.message:"Refund request failed");}finally{setBusy(false);}}
  async function approveRefund(refundId:string){if(!token||approvalPhrase!=="REFUND"||approvalReason.trim().length<8)return;setBusy(true);try{await adminPost(`/refunds/${refundId}/approve`,token,{reason:approvalReason});toast("Refund approved and submitted through the existing payment service");setApprovalReason("");setApprovalPhrase("");q.reload();}catch(e){toast(e instanceof Error?e.message:"Refund approval failed");q.reload();}finally{setBusy(false);}}
  async function rejectRefund(refundId:string){if(!token||approvalReason.trim().length<8)return;setBusy(true);try{await adminPost(`/refunds/${refundId}/reject`,token,{reason:approvalReason});toast("Refund request rejected");setApprovalReason("");q.reload();}catch(e){toast(e instanceof Error?e.message:"Refund rejection failed");q.reload();}finally{setBusy(false);}}

  return <><AdminPage eyebrow="RISK & SUPPORT" title="Dispute detail" description="Review the linked booking, preserve the event history, and route every refund through the existing finance approval service." action={<Link className="button button-secondary" href={`/admin/refunds?booking_id=${q.data?.booking_id??""}`}>Open refund desk</Link>}/>
    <AdminLoad loading={q.loading} error={q.error} data={q.data} retry={q.reload}>{(d)=><div className="admin-dispute-layout">
      <div className="admin-stack"><AdminCard title="Dispute and booking"><div className="admin-detail-grid">{[["Dispute ID",d.id],["Booking ID",d.booking_id],["Reason",d.reason],["Status",d.status],["Customer",d.customer_name],["Customer contact",d.customer_phone],["Vendor",d.vendor_name],["Vendor contact",d.vendor_phone],["Dispute amount",formatAdminMoney(d.amount_inr)],["Payment amount",formatAdminMoney(d.payment_amount)],["Booking status",d.booking_status],["Payment status",d.payment_status],["Created",formatAdminDate(d.created_at,true)],["Updated",formatAdminDate(d.updated_at,true)]].map(([key,value])=><div className="admin-detail-item" key={key}><small>{key}</small><strong>{value}</strong></div>)}</div></AdminCard>
        <AdminCard title="Evidence" subtitle="Evidence upload/storage is not connected; no attachment is represented as uploaded">{d.evidence.length?JSON.stringify(d.evidence):"No evidence attached."}</AdminCard></div>
      <div className="admin-stack"><AdminCard title="Conversation and event timeline"><div className="admin-timeline">{d.timeline.length?d.timeline.map((event,index)=><div className="admin-timeline-row" key={`${event.event_type}-${index}`}><strong>{event.event_type.replaceAll("_"," ")}</strong> · {event.actor_type} · {event.message??"—"}<small>{formatAdminDate(event.created_at,true)}</small></div>):<p>No events recorded.</p>}</div></AdminCard></div>
      <div className="admin-stack">{canManageDisputes&&<AdminCard title="Resolution controls"><form onSubmit={submit}><label className="admin-reason">Action<SelectAction value={action} onChange={setAction}/></label><label className="admin-reason">Reason or note<textarea className="admin-filter" required minLength={4} maxLength={2000} value={message} onChange={(e)=>setMessage(e.target.value)} placeholder="Add context to the immutable timeline"/></label><Button type="submit" disabled={busy||d.status==="closed"||d.status==="resolved"}>{busy?"Saving…":"Record action"}</Button></form></AdminCard>}
        {(canRequestRefund||canApproveRefund)&&<AdminCard title="Refund workflow" subtitle="All financial mutations use the existing audited refund service; dispute actions never change payment or payout amounts.">
          {d.linked_refunds?.length>0&&<div className="admin-stack" style={{marginBottom:14}}>{d.linked_refunds.map(refund=><div className="admin-callout" key={refund.id}>{formatAdminMoney(refund.amount_inr)} · {refund.status} · {refund.reason}
            {refund.status==="requested"&&canApproveRefund&&<><form onSubmit={(event)=>{event.preventDefault();void approveRefund(refund.id);}}><label className="admin-reason">Approval reason<textarea className="admin-filter" required minLength={8} value={approvalReason} onChange={(event)=>setApprovalReason(event.target.value)}/></label><label className="admin-reason">Type REFUND to confirm<input className="admin-filter" required value={approvalPhrase} onChange={(event)=>setApprovalPhrase(event.target.value)}/></label><Button variant="danger" disabled={busy||approvalPhrase!=="REFUND"}>Approve Refund</Button></form><Button variant="secondary" disabled={busy||approvalReason.trim().length<8} onClick={()=>void rejectRefund(refund.id)}>Reject Refund with the reason above</Button></>}</div>)}</div>}
          {canRequestRefund&&<AdminLoad loading={eligibility.loading} error={eligibility.error} data={eligibility.data} retry={eligibility.reload}>
            {(e)=><>
              <div className="admin-detail-grid">
                {[["Original payment",formatAdminMoney(e.amount_inr)],["Previously refunded",formatAdminMoney(e.previously_refunded_amount)],["Remaining refundable",formatAdminMoney(e.remaining_refundable_amount)],["Requested refund",formatAdminMoney(refundAmount||e.remaining_refundable_amount)],["Balance after request",formatAdminMoney(Math.max(0,Number(e.remaining_refundable_amount)-Number(refundAmount||e.remaining_refundable_amount)))],["Payment status",e.payment_status]].map(([label,value])=><div className="admin-detail-item" key={label}><small>{label}</small><strong>{value}</strong></div>)}
              </div>
              {!e.eligible ? (
                <div className="admin-note">Refund unavailable{e.active_refund?": another request is pending or processing":" for the verified payment state"}.</div>
              ) : (
                <form onSubmit={requestRefund}>
                  <label className="admin-reason">Requested amount in INR (blank requests remaining balance)<input className="admin-filter" type="number" min="0.01" max={e.remaining_refundable_amount} step="0.01" value={refundAmount} onChange={(event)=>setRefundAmount(event.target.value)}/></label>
                  <label className="admin-reason">Refund reason<textarea className="admin-filter" required minLength={8} maxLength={1000} value={refundReason} onChange={(event)=>setRefundReason(event.target.value)}/></label>
                  <Button variant="danger" disabled={busy||Boolean(refundAmount&&Number(refundAmount)>Number(e.remaining_refundable_amount))}>{busy?"Submitting…":"Request full or partial refund"}</Button>
                </form>
              )}
            </>}
          </AdminLoad>}</AdminCard>}
      </div>
    </div>}</AdminLoad>
  </>;
}

function SelectAction({value,onChange}:{value:string;onChange:(value:string)=>void}){return <FilterSelect value={value} onChange={(event)=>onChange(event.target.value)}>{[["investigate","Move to investigating"],["await_customer","Request customer information"],["await_vendor","Request vendor information"],["note","Add admin note"],["escalate","Escalate"],["resolve","Resolve"],["close","Close"],["reject","Reject and close"]].map(([key,label])=><option key={key} value={key}>{label}</option>)}</FilterSelect>;}
