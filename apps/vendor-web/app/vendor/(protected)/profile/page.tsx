"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { FormEvent, useState } from "react";
import { apiPatch, apiPost } from "@/services/api";
import { Button, ErrorState, Icon, PageHeader, Panel, SectionHeading, Skeleton, StatePill, toast, useAccessToken, useVendorQuery } from "@/components/portal";
import type { VendorProfile } from "@/types/vendor";
import type { SelectedLocation } from "@/components/location-picker";

const LocationPicker = dynamic(() => import("@/components/location-picker"), {
  ssr: false,
  loading: () => <div className="location-map-loading" role="status">Loading map…</div>,
});

const missingProfile = "No vendor profile is linked to this account";

export default function VendorProfilePage() {
  const token = useAccessToken();
  const profile = useVendorQuery<VendorProfile>("/profile", token);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [selectedLocation, setSelectedLocation] = useState<SelectedLocation | null>(null);
  const needsSetup = profile.error?.includes(missingProfile) ?? false;
  const reviewStatus = profile.data?.verification_status ?? (profile.data?.is_verified ? "approved" : "pending");

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const form = new FormData(event.currentTarget);
    const latValue = form.get("lat");
    const lngValue = form.get("lng");
    const lat = typeof latValue === "string" && latValue.trim() ? Number(latValue) : Number.NaN;
    const lng = typeof lngValue === "string" && lngValue.trim() ? Number(lngValue) : Number.NaN;
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || lat < -90 || lat > 90 || lng < -180 || lng > 180) {
      toast("Choose and confirm the business location on the map first");
      return;
    }
    const value = {
      name: String(form.get("name")).trim(),
      type: String(form.get("type")),
      phone: String(form.get("phone")).trim() || null,
      address: String(form.get("address")).trim(),
      lat,
      lng,
      description: String(form.get("description")).trim() || null,
      image_url: String(form.get("image_url")).trim() || null,
      operating_hours: String(form.get("operating_hours")).trim() || null,
    };
    setBusy(true);
    try {
      const resubmitting = !needsSetup && profile.data?.verification_status === "changes_requested";
      if (needsSetup) await apiPost("/profile", token, value);
      else await apiPatch("/profile", token, value);
      profile.reload();
      setEditing(false);
      toast(needsSetup ? "Profile submitted for VoltStop review" : resubmitting ? "Updated profile resubmitted for VoltStop review" : "Business profile updated");
    } catch (reason) { toast(reason instanceof Error ? reason.message : "Could not save profile"); }
    finally { setBusy(false); }
  }

  return <>
    <PageHeader eyebrow="BUSINESS IDENTITY" title="Business profile" description="Your business details are shown to drivers after the location is verified." action={profile.data && !editing && <Button variant="secondary" onClick={() => setEditing(true)}><Icon name="settings"/>Edit profile</Button>}/>
    {profile.loading ? <Panel className="panel-pad"><Skeleton rows={8}/></Panel> : profile.error && !needsSetup ? <Panel><ErrorState message={profile.error} onRetry={profile.reload}/></Panel> : (editing || needsSetup) ? <Panel className="panel-pad">
      {needsSetup && <div className="status-banner" style={{ marginBottom: 18 }}>Complete your business details and confirm the map pin. Submitting creates a pending application in Admin → Vendor Onboarding; the listing stays hidden from drivers until an administrator approves it.</div>}
      <SectionHeading title={needsSetup ? "Set up your location" : "Edit business details"} detail="This information is tied to the signed-in Supabase account."/>
      <form onSubmit={save}><div className="form-grid">
        <label className="label-control">Business name<input required minLength={1} maxLength={160} name="name" className="input-control" defaultValue={profile.data?.name ?? ""}/></label>
        <label className="label-control">Business type<select name="type" className="select-control" defaultValue={profile.data?.type ?? "restaurant"}><option value="restaurant">Highway Dhaba / Restaurant</option><option value="hotel">Hotel / Stay</option></select></label>
        <label className="label-control">Phone<input name="phone" type="tel" className="input-control" defaultValue={profile.data?.phone ?? ""}/></label>
        <label className="label-control">Operating hours<input name="operating_hours" className="input-control" placeholder="e.g. Daily 06:00–23:00" defaultValue={profile.data?.operating_hours ?? ""}/></label>
        <label className="label-control form-span-2">Business address<input required name="address" maxLength={500} className="input-control" defaultValue={profile.data?.address ?? ""}/><span className="label-note">Enter the address shown to customers. Confirm the precise pin below.</span></label>
        <div className="form-span-2"><span className="label-control">Business location</span><LocationPicker initialValue={profile.data ? { lat: profile.data.lat, lng: profile.data.lng } : null} onConfirm={(location) => setSelectedLocation(location)}/><input type="hidden" name="lat" value={selectedLocation?.lat ?? profile.data?.lat ?? ""}/><input type="hidden" name="lng" value={selectedLocation?.lng ?? profile.data?.lng ?? ""}/></div>
        <label className="label-control form-span-2">Photo URL <span className="label-note">Optional HTTPS image link displayed in driver discovery.</span><input name="image_url" type="url" className="input-control" placeholder="https://…" defaultValue={profile.data?.image_url ?? ""}/></label>
        <label className="label-control form-span-2">Description<textarea name="description" className="textarea-control" maxLength={4000} defaultValue={profile.data?.description ?? ""}/></label>
      </div><div className="form-actions">{!needsSetup && <Button type="button" variant="secondary" onClick={() => setEditing(false)}>Cancel</Button>}<Button disabled={busy}>{busy ? "Saving…" : needsSetup ? "Submit for admin review" : "Save changes"}</Button></div></form>
    </Panel> : profile.data && <div className="dashboard-column">
      {reviewStatus === "approved" && profile.data.is_active && profile.data.is_verified ? <div className="status-banner status-banner-success"><Icon name="check"/>Your business is approved and visible to VoltStop drivers. Charging details are partner-reported unless a live provider is shown.</div> : <div className="status-banner"><Icon name="clock"/>
        {reviewStatus === "changes_requested" ? <>VoltStop requested changes before approval. Edit and save your business details to resubmit the application. {profile.data.decision_reason && <strong>Reviewer note: {profile.data.decision_reason}</strong>}</> :
         reviewStatus === "rejected" ? <>This application was not approved. Contact VoltStop support if you need clarification. {profile.data.decision_reason && <strong>Reviewer note: {profile.data.decision_reason}</strong>}</> :
         reviewStatus === "suspended" ? <>This listing is suspended and hidden from driver discovery. Contact VoltStop support for next steps. {profile.data.decision_reason && <strong>Reviewer note: {profile.data.decision_reason}</strong>}</> :
         profile.data.is_verified ? "Your business is verified and waiting for activation." : reviewStatus === "under_review" ? "Your application is being reviewed by VoltStop. It remains hidden from driver discovery until approval." : "Your business profile is awaiting VoltStop review. It remains hidden from driver discovery until approval."}
      </div>}
      <Panel className="business-hero"><div className="business-image">{profile.data.image_url ? <img src={profile.data.image_url} alt={`${profile.data.name} exterior`}/> : <Icon name="store" size={39}/>}</div><div><div className="table-actions"><h2>{profile.data.name}</h2><StatePill value={profile.data.is_active ? "available" : "closed"}/></div><p>{profile.data.address}</p><p>{profile.data.type === "hotel" ? "Hotel / Stay" : "Highway Dhaba / Restaurant"} · {profile.data.phone || "Phone not listed"}</p></div></Panel>
      <Panel className="panel-pad"><SectionHeading title="Business information" action={<Link className="action-link" href="/vendor/services">Manage services <Icon name="arrow" size={13}/></Link>}/><div className="detail-grid"><div className="detail-field"><span>Business name</span><strong>{profile.data.name}</strong></div><div className="detail-field"><span>Operating hours</span><strong>{profile.data.operating_hours || "Not listed"}</strong></div><div className="detail-field"><span>Address</span><strong>{profile.data.address}</strong></div><div className="detail-field"><span>Photo</span><strong>{profile.data.image_url ? "Linked image" : "No photo linked"}</strong></div></div>{profile.data.description && <p className="page-description" style={{ marginTop: 19 }}>{profile.data.description}</p>}</Panel>
      <Panel className="panel-pad"><SectionHeading title="Saved business location" detail={profile.data.address}/><LocationPicker readOnly initialValue={{ lat: profile.data.lat, lng: profile.data.lng }}/></Panel>
      <Panel className="panel-pad"><SectionHeading title="Services listed" action={<Link className="action-link" href="/vendor/services">Edit services <Icon name="arrow" size={13}/></Link>}/>{!profile.data.services?.length ? <p className="page-description">No services listed yet.</p> : <div className="mini-stats">{profile.data.services.map((service) => <div className="mini-stat" key={service.id}><strong>{service.display_name || service.service_type.replaceAll("_", " ")}</strong><span>{service.is_active ? "ACTIVE" : "PAUSED"}</span></div>)}</div>}</Panel>
    </div>}
  </>;
}
