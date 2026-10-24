"use client";

import { FormEvent, useMemo, useState } from "react";
import { apiDelete, apiPatch, apiPost } from "@/services/api";
import { Button, ErrorState, formatDate, formatMoney, formatTime, Icon, PageHeader, Panel, SectionHeading, Skeleton, StatePill, toast, useAccessToken, useVendorQuery } from "@/components/portal";
import type { VendorService, VendorSlot } from "@/types/vendor";

const hours = Array.from({ length: 15 }, (_, index) => index + 7);
const serviceOptions = ["charging", "food", "sleep_and_charge", "room", "parking", "rest_area", "combo"];

export default function AvailabilityPage() {
  const token = useAccessToken();
  const slots = useVendorQuery<VendorSlot[]>("/availability", token);
  const services = useVendorQuery<VendorService[]>("/services", token);
  const [week, setWeek] = useState(0);
  const [dialog, setDialog] = useState<"create" | VendorSlot | null>(null);
  const [deletingSlotId, setDeletingSlotId] = useState<string | null>(null);
  const monday = useMemo(() => {
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    date.setDate(date.getDate() - ((date.getDay() + 6) % 7) + week * 7);
    return date;
  }, [week]);
  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => { const date = new Date(monday); date.setDate(date.getDate() + index); return date; }), [monday]);

  function status(slot: VendorSlot) {
    if (slot.locked) return "locked";
    if (slot.status === "closed") return "closed";
    if (slot.status === "booked" || slot.active_bookings >= slot.capacity) return "booked";
    if (slot.active_bookings > 0) return "limited";
    return "available";
  }

  const visible = (slots.data ?? []).filter((slot) => {
    const start = new Date(slot.slot_start_time);
    return start >= monday && start < new Date(days[6].getTime() + 86400000);
  });

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !dialog) return;
    const form = new FormData(event.currentTarget);
    const update = {
      slot_start_time: new Date(String(form.get("start"))).toISOString(),
      slot_end_time: new Date(String(form.get("end"))).toISOString(),
      capacity: Number(form.get("capacity")),
      price_inr: Number(form.get("price")),
      service_type: String(form.get("service_type")),
      ...(dialog === "create" ? {} : { status: String(form.get("status")) }),
    };
    try {
      if (dialog === "create") await apiPost("/availability", token, update);
      else await apiPatch(`/availability/${dialog.id}`, token, update);
      setDialog(null);
      slots.reload();
      toast(dialog === "create" ? "Availability slot created" : "Slot updated");
    } catch (reason) { toast(reason instanceof Error ? reason.message : "Could not save slot"); }
  }

  function deletionBlockedReason(slot: VendorSlot): string | null {
    if (slot.locked) return "A driver is holding this slot";
    if (slot.booking_history > 0) return "Slots with booking history are retained";
    if (new Date(slot.slot_start_time).getTime() <= Date.now()) return "Past and in-progress slots are retained";
    return null;
  }

  async function removeSlot(slot: VendorSlot) {
    if (!token || deletionBlockedReason(slot)) return;
    if (!window.confirm("Delete this availability slot? This can’t be undone.")) return;
    setDeletingSlotId(slot.id);
    try {
      await apiDelete(`/availability/${slot.id}`, token);
      slots.reload();
      toast("Availability slot deleted");
    } catch (reason) {
      toast(reason instanceof Error ? reason.message : "Could not delete slot");
    } finally {
      setDeletingSlotId(null);
    }
  }

  return <>
    <PageHeader eyebrow="CAPACITY PLANNING" title="Availability" description="Plan your schedule. Slots with an active driver hold or booking stay protected." action={<Button disabled={!services.data?.some((service) => service.is_active)} onClick={() => setDialog("create")}><Icon name="calendar"/>Add slot</Button>}/>
    {!services.loading && !services.error && !services.data?.some((service) => service.is_active) && <Panel className="status-banner" style={{ marginBottom: 16 }}>Create and enable a service before adding a bookable time slot.</Panel>}
    {slots.loading ? <Panel className="panel-pad"><Skeleton rows={10}/></Panel> : slots.error ? <Panel><ErrorState message={slots.error} onRetry={slots.reload}/></Panel> : <Panel className="calendar-scroll">
      <div className="calendar-toolbar"><div><strong style={{ fontSize: 13 }}>{formatDate(days[0], { day: "numeric", month: "long" })} – {formatDate(days[6], { day: "numeric", month: "long", year: "numeric" })}</strong><span className="table-secondary">{visible.length} slots scheduled · {visible.filter((slot) => status(slot) === "available" || status(slot) === "limited").length} currently open</span></div><div className="table-actions"><Button variant="secondary" onClick={() => setWeek((value) => value - 1)} aria-label="Previous week">‹</Button><Button variant="secondary" onClick={() => setWeek(0)}>Today</Button><Button variant="secondary" onClick={() => setWeek((value) => value + 1)} aria-label="Next week">›</Button></div></div>
      <div className="calendar-grid"><div className="calendar-head"><div>LOCAL TIME</div>{days.map((day) => <div key={day.toISOString()}>{formatDate(day, { weekday: "short", day: "numeric" })}</div>)}</div>
        {hours.map((hour) => <div className="calendar-row" key={hour}><div className="calendar-hour">{formatTime(new Date(2000, 0, 1, hour))}</div>{days.map((day) => {
          const matches = visible.filter((slot) => { const start = new Date(slot.slot_start_time); return start.toDateString() === day.toDateString() && start.getHours() === hour; });
          return <div className="calendar-cell" key={day.toISOString()}>{matches.map((slot) => <button key={slot.id} onClick={() => setDialog(slot)} title={`${slot.service_type} · ${formatMoney(slot.price_inr)}`} className={`slot-chip ${status(slot) === "closed" ? "closed" : ""}`}><span>{formatTime(slot.slot_start_time)} · {status(slot)}</span></button>)}</div>;
        })}</div>)}
      </div>
      {!visible.length && <div style={{ padding: 16 }}><p className="page-description">No slots are scheduled for this week. Add a slot to publish availability.</p></div>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 9, padding: "13px 17px", borderTop: "1px solid var(--line)" }}>{["available", "limited", "full", "closed", "locked", "booked"].map((state) => <StatePill key={state} value={state}/>)}</div>
    </Panel>}
    <Panel className="panel-pad" style={{ marginTop: 18 }}><SectionHeading title="Upcoming and past slots" detail="Delete future slots only when they have no booking history or active driver hold."/>{slots.loading ? <Skeleton rows={4}/> : slots.error ? <p className="page-description">Slot history unavailable.</p> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Date</th><th>Time</th><th>Service</th><th>Capacity</th><th>Price</th><th>Bookings</th><th>Status</th><th>Action</th></tr></thead><tbody>{(slots.data ?? []).slice(0, 50).map((slot) => { const blockedReason = deletionBlockedReason(slot); return <tr key={slot.id}><td>{formatDate(slot.slot_start_time)}</td><td>{formatTime(slot.slot_start_time)} – {formatTime(slot.slot_end_time)}</td><td>{slot.service_type.replaceAll("_", " ")}</td><td>{slot.active_bookings} / {slot.capacity}</td><td>{formatMoney(slot.price_inr)}</td><td>{slot.booking_history}</td><td><StatePill value={status(slot)}/></td><td><div className="table-actions"><button className="action-link" disabled={slot.locked || slot.status === "booked"} onClick={() => setDialog(slot)}>Edit</button><button className="action-link action-link-danger" disabled={Boolean(blockedReason) || deletingSlotId === slot.id} title={blockedReason ?? "Delete this slot"} onClick={() => void removeSlot(slot)}>{deletingSlotId === slot.id ? "Deleting…" : "Delete"}</button></div></td></tr>; })}</tbody></table></div>}</Panel>
    {dialog && <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setDialog(null)}><div className="modal-card"><div className="modal-head"><div><h2>{dialog === "create" ? "Add availability" : "Edit slot"}</h2><p>Slot changes are checked against active bookings and driver holds.</p></div><button className="close-button" onClick={() => setDialog(null)}><Icon name="close"/></button></div>
      <form onSubmit={save}><div className="form-grid"><label className="label-control">Starts<input required name="start" type="datetime-local" className="input-control" defaultValue={dialog === "create" ? "" : toLocalInput(dialog.slot_start_time)}/></label><label className="label-control">Ends<input required name="end" type="datetime-local" className="input-control" defaultValue={dialog === "create" ? "" : toLocalInput(dialog.slot_end_time)}/></label>
        <label className="label-control">Service<select name="service_type" className="select-control" defaultValue={dialog === "create" ? services.data?.find((item) => item.is_active)?.service_type ?? "charging" : dialog.service_type}>{(services.data ?? []).filter((item) => item.is_active).map((service) => <option key={service.id} value={service.service_type}>{service.display_name ?? service.service_type.replaceAll("_", " ")}</option>)}</select></label>
        <label className="label-control">Capacity<input required min="1" max="10000" name="capacity" type="number" className="input-control" defaultValue={dialog === "create" ? 1 : dialog.capacity}/></label>
        <label className="label-control">Price (INR)<input required min="0" step="0.01" name="price" type="number" className="input-control" defaultValue={dialog === "create" ? "" : dialog.price_inr}/></label>
        {dialog !== "create" && <label className="label-control">Availability<select name="status" className="select-control" defaultValue={dialog.status === "closed" ? "closed" : "available"}><option value="available">Open</option><option value="closed">Close slot</option></select></label>}
      </div>{dialog !== "create" && dialog.booking_history > 0 && <p className="warning-copy" style={{ marginTop: 14 }}>This slot has booking history and will be retained. Time, service and price edits are blocked while active bookings exist.</p>}<div className="form-actions"><Button type="button" variant="secondary" onClick={() => setDialog(null)}>Cancel</Button><Button type="submit">Save slot</Button></div></form></div></div>}
  </>;
}

function toLocalInput(value: string) {
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}
