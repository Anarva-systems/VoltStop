"use client";

import { useState } from "react";
import { adminPost, adminPatch } from "@/services/admin-api";
import { toast } from "@/components/portal";
import { AdminCard, AdminLoad, AdminPage, AdminTable, StateBadge, formatAdminDate, useAdminQuery, useAdminToken } from "@/components/admin-ui";
type Notice = { id: string; booking_id: string | null; type: string; title: string; message: string; read_at: string | null; created_at: string };
type NoticePage = { items: Notice[]; total: number; unread: number };
export default function NotificationsPage() {
  const token=useAdminToken(); const [unreadOnly,setUnreadOnly]=useState(false); const q=useAdminQuery<NoticePage>(`/notifications?limit=100${unreadOnly?"&unread_only=true":""}`,token);
  async function read(id:string){if(!token)return;try{await adminPatch(`/notifications/${id}/read`,token,{});q.reload();}catch(error){toast(error instanceof Error?error.message:"Could not update notification");}}
  async function readAll(){if(!token)return;try{await adminPost("/notifications/read-all",token);q.reload();toast("Notifications marked as read");}catch(error){toast(error instanceof Error?error.message:"Could not update notifications");}}
  return <><AdminPage title="Notifications" description="Persisted alerts delivered to your administrator account for booking, restaurant order, hotel reservation, and support events." action={<button className="admin-button admin-button-secondary" onClick={()=>void readAll()} disabled={!q.data?.unread}>Mark all read ({q.data?.unread??0})</button>}/><AdminCard><div className="admin-toolbar"><label className="admin-inline-check"><input type="checkbox" checked={unreadOnly} onChange={(event)=>setUnreadOnly(event.target.checked)}/>Unread only</label><span>{q.data?.total??0} notifications · {q.data?.unread??0} unread</span></div><AdminLoad loading={q.loading} error={q.error} data={q.data} retry={q.reload} empty={Boolean(q.data&&!q.data.items.length)} emptyTitle="No notifications yet">{(data)=><AdminTable headers={["Notification","Type","Reference","Created","Read state","Action"]}>{data.items.map((item)=><tr key={item.id}><td><strong>{item.title}</strong><small style={{display:"block",whiteSpace:"normal"}}>{item.message}</small></td><td>{item.type.replaceAll("_"," ")}</td><td>{item.booking_id||"—"}</td><td>{formatAdminDate(item.created_at,true)}</td><td><StateBadge value={item.read_at?"read":"unread"}/></td><td>{item.read_at?"—":<button className="action-link" onClick={()=>void read(item.id)}>Mark read</button>}</td></tr>)}</AdminTable>}</AdminLoad></AdminCard></>;
}
