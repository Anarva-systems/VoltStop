"use client";

import { FormEvent, useState } from "react";
import { apiPatch, apiPost } from "@/services/api";
import { Button, EmptyState, ErrorState, formatMoney, Icon, PageHeader, Panel, SectionHeading, Skeleton, StatePill, toast, useAccessToken, useVendorQuery } from "@/components/portal";
import type { VendorService } from "@/types/vendor";

const serviceTypes = [
  ["food", "Food"], ["charging", "AC Slow Charging"], ["sleep_and_charge", "Sleep & Charge"],
  ["room", "Room"], ["parking", "Parking"], ["rest_area", "Rest Area"], ["combo", "Combo Package"],
];

export function ServiceManager({ pricingOnly = false }: { pricingOnly?: boolean }) {
  const token = useAccessToken();
  const services = useVendorQuery<VendorService[]>("/services", token);
  const [dialog, setDialog] = useState<"new" | VendorService | null>(null);
  const [busy, setBusy] = useState("");
  const [prices, setPrices] = useState<Record<string, string>>({});

  async function saveService(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !dialog) return;
    const form = new FormData(event.currentTarget);
    let availability: Record<string, unknown> = {};
    try { availability = JSON.parse(String(form.get("availability") || "{}")) as Record<string, unknown>; }
    catch { toast("Availability must be valid JSON, for example {\"days\":[\"Mon\",\"Tue\"]}"); return; }
    const value = {
      service_type: String(form.get("service_type")),
      display_name: String(form.get("display_name")).trim(),
      description: String(form.get("description")).trim() || null,
      price_inr: Number(form.get("price_inr")),
      capacity: form.get("capacity") ? Number(form.get("capacity")) : null,
      availability,
      is_active: form.get("is_active") === "on",
    };
    setBusy(dialog === "new" ? "new" : dialog.id);
    try {
      if (dialog === "new") await apiPost("/services", token, value);
      else await apiPatch(`/services/${dialog.id}`, token, value);
      setDialog(null);
      services.reload();
      toast(dialog === "new" ? "Service added" : "Service updated");
    } catch (reason) { toast(reason instanceof Error ? reason.message : "Could not save service"); }
    finally { setBusy(""); }
  }

  async function toggle(service: VendorService) {
    if (!token) return;
    setBusy(service.id);
    try { await apiPatch(`/services/${service.id}`, token, { is_active: !service.is_active }); services.reload(); toast(service.is_active ? "Service paused" : "Service enabled"); }
    catch (reason) { toast(reason instanceof Error ? reason.message : "Could not update service"); }
    finally { setBusy(""); }
  }

  async function updatePrice(service: VendorService, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const next = Number(prices[service.id] ?? service.price_inr);
    if (!Number.isFinite(next) || next < 0) { toast("Enter a valid price in INR"); return; }
    setBusy(service.id);
    try { await apiPatch(`/services/${service.id}`, token, { price_inr: next }); services.reload(); toast("Price updated"); }
    catch (reason) { toast(reason instanceof Error ? reason.message : "Could not update price"); }
    finally { setBusy(""); }
  }

  const pageTitle = pricingOnly ? "Pricing" : "Services";
  return <>
    <PageHeader eyebrow={pricingOnly ? "SERVICE RATES" : "OFFERINGS"} title={pricingOnly ? "Pricing" : "Services & packages"} description={pricingOnly ? "Set your INR prices. Driver-facing prices update from this service catalogue." : "Manage the services drivers can discover and reserve at your location."} action={!pricingOnly && <Button onClick={() => setDialog("new")}><Icon name="bolt"/>Add service</Button>}/>
    {services.loading ? <div className="service-grid">{Array.from({ length: 4 }, (_, index) => <Panel key={index} className="panel-pad"><Skeleton rows={4}/></Panel>)}</div> : services.error ? <Panel><ErrorState message={services.error} onRetry={services.reload}/></Panel> : !services.data?.length ? <Panel><EmptyState title="No services set up" description="Add the food, charging and stay options drivers can book at your business." action={<Button onClick={() => setDialog("new")}><Icon name="bolt"/>Add your first service</Button>}/></Panel> : pricingOnly ? <div className="service-grid">{services.data.map((service) => <Panel className="service-card" key={service.id}>
      <div className="service-card-head"><div><h3>{service.display_name || label(service.service_type)}</h3><span className="table-secondary">{label(service.service_type)}</span></div><StatePill value={service.is_active ? "available" : "closed"}/></div>
      <p>{service.description || "No service description added."}</p>
      <form onSubmit={(event) => updatePrice(service, event)} className="form-grid" style={{ gridTemplateColumns: "1fr auto", gap: 8, alignItems: "end" }}><label className="label-control">Price · INR<input className="input-control" type="number" min="0" step="0.01" value={prices[service.id] ?? service.price_inr} onChange={(event) => setPrices((current) => ({ ...current, [service.id]: event.target.value }))}/></label><Button disabled={busy === service.id}>{busy === service.id ? "Saving…" : "Save price"}</Button></form>
      <div className="service-actions"><span className="label-note">{service.capacity ? `Capacity ${service.capacity}` : "Capacity managed by slots"}</span><button className="action-link" onClick={() => setDialog(service)}>Edit service</button></div>
    </Panel>)}</div> : <div className="service-grid">{services.data.map((service) => <Panel className="service-card" key={service.id}>
      <div className="service-card-head"><div><h3>{service.display_name || label(service.service_type)}</h3><span className="table-secondary">{label(service.service_type)}</span></div><span className="metric-icon"><Icon name={service.service_type === "charging" ? "bolt" : "store"}/></span></div>
      <p>{service.description || "Add a short description to help drivers choose this service."}</p><div className="service-price">{formatMoney(service.price_inr)}<small>per reservation</small></div>
      <div className="service-actions"><StatePill value={service.is_active ? "available" : "closed"}/><div className="table-actions"><button className="action-link" onClick={() => setDialog(service)}>Edit</button><Button variant="secondary" disabled={busy === service.id} onClick={() => toggle(service)}>{busy === service.id ? "Saving…" : service.is_active ? "Pause" : "Enable"}</Button></div></div>
    </Panel>)}</div>}
    {pricingOnly && <p className="label-note" style={{ marginTop: 17 }}>This service pricing report shows listed prices; commission and settlement estimates use verified payment records.</p>}
    {dialog && <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setDialog(null)}><div className="modal-card"><div className="modal-head"><div><h2>{dialog === "new" ? "Add a service" : "Edit service"}</h2><p>This service catalogue is used by driver discovery and vendor booking slots.</p></div><button className="close-button" onClick={() => setDialog(null)}><Icon name="close"/></button></div>
      <form onSubmit={saveService}><div className="form-grid">
        <label className="label-control form-span-2">Service name<input required name="display_name" className="input-control" placeholder="AC Slow Charging" defaultValue={dialog === "new" ? "" : dialog.display_name ?? ""}/></label>
        <label className="label-control">Service type<select name="service_type" className="select-control" defaultValue={dialog === "new" ? "charging" : dialog.service_type}>{serviceTypes.map(([value,name]) => <option value={value} key={value}>{name}</option>)}</select></label>
        <label className="label-control">Price · INR<input required min="0" step="0.01" name="price_inr" type="number" className="input-control" defaultValue={dialog === "new" ? "" : dialog.price_inr}/></label>
        <label className="label-control">Capacity per service<input min="1" name="capacity" type="number" className="input-control" placeholder="Managed by slots if blank" defaultValue={dialog === "new" ? "" : dialog.capacity ?? ""}/></label>
        <label className="checkbox-line" style={{ alignSelf: "end", minHeight: 41 }}><input name="is_active" type="checkbox" defaultChecked={dialog === "new" ? true : dialog.is_active}/>Available to drivers</label>
        <label className="label-control form-span-2">Description<textarea name="description" className="textarea-control" placeholder="What is included in this service?" defaultValue={dialog === "new" ? "" : dialog.description ?? ""}/></label>
        <label className="label-control form-span-2">Availability details <span className="label-note">Optional JSON used to describe service hours, e.g. {'{"days":["Mon","Tue"],"open":"08:00","close":"22:00"}'}</span><textarea name="availability" className="textarea-control" defaultValue={dialog === "new" ? "{}" : JSON.stringify(dialog.availability ?? {}, null, 2)}/></label>
      </div><div className="form-actions"><Button type="button" variant="secondary" onClick={() => setDialog(null)}>Cancel</Button><Button disabled={busy !== ""}>{busy ? "Saving…" : dialog === "new" ? "Add service" : "Save changes"}</Button></div></form></div></div>}
  </>;
}

function label(value: string) { return serviceTypes.find(([key]) => key === value)?.[1] ?? value.replaceAll("_", " "); }
