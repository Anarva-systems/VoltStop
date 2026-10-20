"use client";

import { FormEvent, useState } from "react";
import { apiPatch, apiPost } from "@/services/api";
import { Button, EmptyState, ErrorState, formatMoney, Icon, PageHeader, Panel, SectionHeading, Skeleton, StatePill, toast, useAccessToken, useVendorQuery } from "@/components/portal";
import type { VendorService } from "@/types/vendor";

const serviceTypes = [
  ["food", "Food"], ["charging", "AC Slow Charging"], ["sleep_and_charge", "Sleep & Charge"],
  ["room", "Room"], ["parking", "Parking"], ["rest_area", "Rest Area"],
];
const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function stringValue(value: unknown) { return typeof value === "string" ? value : ""; }

export function ServiceManager({ pricingOnly = false }: { pricingOnly?: boolean }) {
  const token = useAccessToken();
  const services = useVendorQuery<VendorService[]>("/services", token);
  const [dialog, setDialog] = useState<"new" | VendorService | null>(null);
  const [busy, setBusy] = useState("");
  const [formError, setFormError] = useState("");
  const [prices, setPrices] = useState<Record<string, string>>({});

  async function saveService(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !dialog) return;
    const form = new FormData(event.currentTarget);
    const serviceType = String(form.get("service_type"));
    if (dialog === "new" && services.data?.some((service) => service.service_type === serviceType)) {
      const existing = services.data.find((service) => service.service_type === serviceType);
      setFormError(`You already list ${existing?.display_name || label(serviceType)}. Edit that service to change its details or price.`);
      return;
    }
    const previousAvailability = dialog === "new" ? {} : dialog.availability ?? {};
    const days = form.getAll("availability_days").map(String);
    const open = String(form.get("availability_open") ?? "");
    const close = String(form.get("availability_close") ?? "");
    if (Boolean(open) !== Boolean(close)) {
      toast("Add both opening and closing times, or leave both blank");
      return;
    }
    const availability: Record<string, unknown> = { ...previousAvailability };
    delete availability.days;
    delete availability.open;
    delete availability.close;
    if (days.length) availability.days = days;
    if (open) availability.open = open;
    if (close) availability.close = close;
    const value = {
      service_type: serviceType,
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
    } catch (reason) { setFormError(reason instanceof Error ? reason.message : "Could not save service"); }
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
    <PageHeader eyebrow={pricingOnly ? "SERVICE RATES" : "OFFERINGS"} title={pricingOnly ? "Pricing" : "Services & packages"} description={pricingOnly ? "Set your INR prices. Driver-facing prices update from this service catalogue." : "Manage the services drivers can discover and reserve at your location."} action={!pricingOnly && <Button onClick={() => { setFormError(""); setDialog("new"); }}><Icon name="bolt"/>Add service</Button>}/>
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
    {dialog && <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setDialog(null)}><div className="modal-card"><div className="modal-head"><div><h2>{dialog === "new" ? "Add a service" : "Edit service"}</h2><p>Choose what drivers can find and reserve at your business.</p></div><button className="close-button" onClick={() => setDialog(null)}><Icon name="close"/></button></div>
      <form onChange={() => setFormError("")} onSubmit={saveService}>{formError && <p className="form-error" role="alert">{formError}</p>}<div className="form-grid">
        <label className="label-control form-span-2">Service name<input required name="display_name" className="input-control" placeholder="e.g. AC charging, breakfast, standard room" defaultValue={dialog === "new" ? "" : dialog.display_name ?? ""}/></label>
        <label className="label-control">Service type<select name="service_type" className="select-control" defaultValue={dialog === "new" ? "charging" : dialog.service_type}>{serviceTypes.map(([value,name]) => <option value={value} key={value}>{name}</option>)}</select></label>
        <label className="label-control">Price per booking · INR<input required min="0" step="0.01" name="price_inr" type="number" className="input-control" placeholder="0.00" defaultValue={dialog === "new" ? "" : dialog.price_inr}/></label>
        <label className="label-control">Capacity per time slot<input min="1" name="capacity" type="number" className="input-control" placeholder="Leave blank to manage in Availability" defaultValue={dialog === "new" ? "" : dialog.capacity ?? ""}/></label>
        <label className="checkbox-line" style={{ alignSelf: "end", minHeight: 41 }}><input name="is_active" type="checkbox" defaultChecked={dialog === "new" ? true : dialog.is_active}/>Available to drivers</label>
        <label className="label-control form-span-2">Description<textarea name="description" className="textarea-control" placeholder="What is included in this service?" defaultValue={dialog === "new" ? "" : dialog.description ?? ""}/></label>
        <fieldset className="service-hours form-span-2"><legend>Opening hours <span className="label-note">Optional · leave blank if this service has no fixed hours</span></legend>
          <span className="label-note">Days available</span>
          <div className="service-days">{weekdays.map((day) => <label className="service-day" key={day}><input name="availability_days" type="checkbox" value={day} defaultChecked={dialog !== "new" && Array.isArray(dialog.availability?.days) && dialog.availability.days.includes(day)}/>{day}</label>)}</div>
          <div className="service-hours-times"><label className="label-control">Opens at<input className="input-control" name="availability_open" type="time" defaultValue={dialog === "new" ? "" : stringValue(dialog.availability.open)}/></label><label className="label-control">Closes at<input className="input-control" name="availability_close" type="time" defaultValue={dialog === "new" ? "" : stringValue(dialog.availability.close)}/></label></div>
          <span className="label-note">These hours help drivers know when to visit. Manage bookable time slots in Availability.</span>
        </fieldset>
      </div><div className="form-actions"><Button type="button" variant="secondary" onClick={() => setDialog(null)}>Cancel</Button><Button disabled={busy !== ""}>{busy ? "Saving…" : dialog === "new" ? "Add service" : "Save changes"}</Button></div></form></div></div>}
  </>;
}

function label(value: string) { return serviceTypes.find(([key]) => key === value)?.[1] ?? value.replaceAll("_", " "); }
