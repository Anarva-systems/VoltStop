"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiPatch } from "@/services/api";
import { Button, ErrorState, Icon, PageHeader, Panel, SectionHeading, Skeleton, toast, useAccessToken, useVendorQuery } from "@/components/portal";
import { useVendorAuth } from "@/components/vendor-auth";
import { supabaseBrowserClient } from "@/services/supabase";

export default function VendorSettingsPage() {
  const { user, signOut } = useVendorAuth();
  const token = useAccessToken();
  const business = useVendorQuery<{name:string;phone:string|null;operating_hours:string|null;address:string}> ("/profile", token);
  const [businessForm, setBusinessForm] = useState({name:"",phone:"",operating_hours:""});
  const [savingBusiness,setSavingBusiness]=useState(false);
  const [editingPassword, setEditingPassword] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(()=>{if(business.data)setBusinessForm({name:business.data.name,phone:business.data.phone??"",operating_hours:business.data.operating_hours??""});},[business.data]);

  async function updateBusiness(event:FormEvent<HTMLFormElement>){event.preventDefault();if(!token)return;setSavingBusiness(true);try{await apiPatch("/profile",token,{name:businessForm.name.trim(),phone:businessForm.phone.trim()||null,operating_hours:businessForm.operating_hours.trim()||null});business.reload();toast("Business settings saved");}catch(reason){toast(reason instanceof Error?reason.message:"Business settings were not saved");}finally{setSavingBusiness(false);}}

  async function updatePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password"));
    if (password !== String(form.get("confirm"))) { toast("Passwords do not match"); return; }
    const client = supabaseBrowserClient();
    if (!client) return;
    setBusy(true);
    try {
      const { error } = await client.auth.updateUser({ password });
      if (error) throw error;
      setEditingPassword(false);
      toast("Password updated");
    } catch (reason) { toast(reason instanceof Error ? reason.message : "Could not update password"); }
    finally { setBusy(false); }
  }

  async function logout() {
    if (!window.confirm("Sign out of the VoltStop partner portal?")) return;
    await signOut();
    window.location.assign("/vendor/login");
  }

  return <>
    <PageHeader eyebrow="ACCOUNT & ACCESS" title="Settings" description="Manage sign-in security and review how your account is connected."/>
    <div className="dashboard-column">
      <Panel className="panel-pad"><SectionHeading title="Signed-in account" detail="Authenticated through Supabase; vendor ownership is checked by the API."/><div className="detail-grid"><div className="detail-field"><span>Email</span><strong>{user?.email ?? "Not available"}</strong></div><div className="detail-field"><span>Account ID</span><strong>{user?.id ?? "—"}</strong></div><div className="detail-field"><span>Phone</span><strong>{user?.phone ?? "Not connected"}</strong></div><div className="detail-field"><span>Authentication</span><strong>{user?.app_metadata?.provider ?? "Supabase"}</strong></div></div></Panel>
      <Panel className="panel-pad"><SectionHeading title="Business preferences" detail="These fields are saved to your authorized vendor profile and used by the listing."/>{business.loading?<Skeleton rows={3}/>:business.error?<ErrorState message={business.error} onRetry={business.reload}/>:<form onSubmit={updateBusiness}><div className="form-grid"><label className="label-control">Business name<input className="input-control" minLength={1} maxLength={160} required value={businessForm.name} onChange={(e)=>setBusinessForm({...businessForm,name:e.target.value})}/></label><label className="label-control">Business contact phone<input className="input-control" maxLength={40} value={businessForm.phone} onChange={(e)=>setBusinessForm({...businessForm,phone:e.target.value})}/></label><label className="label-control">Operating hours<input className="input-control" maxLength={1000} value={businessForm.operating_hours} onChange={(e)=>setBusinessForm({...businessForm,operating_hours:e.target.value})} placeholder="For example: Mon–Sun, 08:00–22:00"/></label><div className="detail-field"><span>Business address</span><strong>{business.data?.address??"—"}</strong></div></div><div className="form-actions"><Button type="button" variant="secondary" onClick={()=>business.data&&setBusinessForm({name:business.data.name,phone:business.data.phone??"",operating_hours:business.data.operating_hours??""})}>Cancel changes</Button><Button disabled={savingBusiness}>{savingBusiness?"Saving…":"Save business settings"}</Button></div></form>}</Panel>
      <Panel className="panel-pad"><SectionHeading title="Password & security" detail="Update your Supabase account password."/>{!editingPassword ? <div className="table-actions"><Button variant="secondary" onClick={() => setEditingPassword(true)}>Change password</Button><span className="label-note">Signed-in access tokens are sent to VoltStop API over the configured API URL.</span></div> : <form onSubmit={updatePassword}><div className="form-grid"><label className="label-control">New password<input required minLength={8} type="password" name="password" autoComplete="new-password" className="input-control"/></label><label className="label-control">Confirm new password<input required minLength={8} type="password" name="confirm" autoComplete="new-password" className="input-control"/></label></div><div className="form-actions"><Button type="button" variant="secondary" onClick={() => setEditingPassword(false)}>Cancel</Button><Button disabled={busy}>{busy ? "Updating…" : "Update password"}</Button></div></form>}</Panel>
      <Panel className="panel-pad"><SectionHeading title="Portal configuration"/><div className="detail-grid"><div className="detail-field"><span>API base URL</span><strong>{process.env.NEXT_PUBLIC_API_URL || "Not configured for this deployment"}</strong></div><div className="detail-field"><span>Business listing</span><strong>Profile approval required before driver discovery</strong></div></div><div style={{ marginTop: 16 }}><Link className="action-link" href="/vendor/profile">Review business profile <Icon name="arrow" size={13}/></Link></div></Panel>
      <Panel className="panel-pad"><SectionHeading title="Sign out" detail="This clears the active Supabase session in this browser."/><Button variant="danger" onClick={logout}><Icon name="logout"/>Sign out</Button></Panel>
    </div>
  </>;
}
