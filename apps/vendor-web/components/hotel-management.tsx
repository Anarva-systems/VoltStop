"use client";

import { FormEvent, useState } from "react";
import { apiGet, apiPost, apiPatch, vendorApi } from "@/services/api";
import { Button, EmptyState, ErrorState, formatDate, formatMoney, Icon, PageHeader, Panel, SectionHeading, Skeleton, StatePill, toast, useAccessToken, useVendorQuery } from "@/components/portal";

type Room = { id: string; name: string; description: string | null; max_guests: number; base_rate_inr: number; total_rooms: number; free_cancellation_hours: number; is_active: boolean };
type Inventory = { stay_date: string; room_capacity: number; rooms_available: number; nightly_rate_inr: number };
type Reservation = { id: string; check_in: string; check_out: string; guests: number; rooms: number; amount_inr: number; status: string; payment_status: string | null; webhook_verified: boolean | null; room_name: string; customer_name: string | null; customer_phone: string | null };

export function HotelManagement() {
  const token = useAccessToken();
  const rooms = useVendorQuery<Room[]>("/hotels/rooms", token);
  const reservations = useVendorQuery<Reservation[]>("/hotels/reservations", token);
  const [editing, setEditing] = useState<Room | "new" | null>(null);
  const [activeRoom, setActiveRoom] = useState<string | null>(null);
  const [inventory, setInventory] = useState<Inventory[]>([]);
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [capacity, setCapacity] = useState("1");
  const [available, setAvailable] = useState("1");
  const [rate, setRate] = useState("");
  const [busy, setBusy] = useState(false);

  async function saveRoom(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!token || !editing) return;
    const form = new FormData(event.currentTarget);
    const value = { name: String(form.get("name")).trim(), description: String(form.get("description")).trim() || null,
      max_guests: Number(form.get("max_guests")), base_rate_inr: Number(form.get("base_rate_inr")),
      total_rooms: Number(form.get("total_rooms")), free_cancellation_hours: Number(form.get("free_cancellation_hours")), is_active: form.get("is_active") === "on" };
    setBusy(true);
    try { if (editing === "new") await apiPost("/hotels/rooms", token, value); else await apiPatch(`/hotels/rooms/${editing.id}`, token, value);
      setEditing(null); rooms.reload(); toast("Room type saved"); }
    catch (error) { toast(error instanceof Error ? error.message : "Room type could not be saved"); }
    finally { setBusy(false); }
  }

  async function loadInventory(room: Room) {
    if (!token) return;
    setActiveRoom(room.id); setCapacity(String(room.total_rooms)); setAvailable(String(room.total_rooms)); setRate(String(room.base_rate_inr));
    try {
      const end = new Date(`${date}T00:00:00`); end.setDate(end.getDate() + 31);
      const rows = await apiGet<Inventory[]>(`/hotels/rooms/${room.id}/inventory?start=${date}&end=${end.toISOString().slice(0, 10)}`, token);
      setInventory(rows);
    } catch (error) { toast(error instanceof Error ? error.message : "Inventory could not be loaded"); }
  }

  async function saveInventory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!token || !activeRoom) return;
    setBusy(true);
    try {
      await vendorApi(`/hotels/rooms/${activeRoom}/inventory`, token, { method: "PUT", body: JSON.stringify({ stay_date: date, room_capacity: Number(capacity), rooms_available: Number(available), nightly_rate_inr: Number(rate) }) });
      const room = rooms.data?.find((item) => item.id === activeRoom); if (room) await loadInventory(room);
      toast("Nightly inventory saved");
    } catch (error) { toast(error instanceof Error ? error.message : "Inventory could not be saved"); }
    finally { setBusy(false); }
  }

  async function toggle(room: Room) {
    if (!token) return; setBusy(true);
    try { await apiPatch(`/hotels/rooms/${room.id}`, token, { is_active: !room.is_active }); rooms.reload(); toast(room.is_active ? "Room type paused" : "Room type enabled"); }
    catch (error) { toast(error instanceof Error ? error.message : "Room type could not be updated"); }
    finally { setBusy(false); }
  }

  return <>
    <PageHeader eyebrow="STAYS" title="Hotel rooms & reservations" description="Manage room types, dated nightly inventory and guest reservations. Availability is checked and allocated by the server for every night." action={<Button onClick={() => setEditing("new")}><Icon name="hotel"/>Add room type</Button>} />
    <SectionHeading title="Room types" detail="Rates and guest capacity for each bookable room category." />
    {rooms.loading ? <Panel><Skeleton rows={5}/></Panel> : rooms.error ? <Panel><ErrorState message={rooms.error} onRetry={rooms.reload}/></Panel> : !rooms.data?.length ? <Panel><EmptyState title="No room types yet" description="Create a room type before publishing nightly inventory." action={<Button onClick={() => setEditing("new")}>Add room type</Button>}/></Panel> : <div className="service-grid">{rooms.data.map((room) => <Panel className="service-card" key={room.id}>
      <div className="service-card-head"><div><h3>{room.name}</h3><span className="table-secondary">Up to {room.max_guests} guests · {room.total_rooms} rooms</span></div><StatePill value={room.is_active ? "available" : "closed"}/></div>
      <p>{room.description || "No room description added."}</p><div className="service-price">{formatMoney(room.base_rate_inr)}<small>base rate / night</small></div>
      <div className="service-actions"><span className="label-note">Free cancellation until {room.free_cancellation_hours}h before check-in</span><div className="table-actions"><button className="action-link" onClick={() => setEditing(room)}>Edit</button><Button variant="secondary" disabled={busy} onClick={() => toggle(room)}>{room.is_active ? "Pause" : "Enable"}</Button><Button variant="secondary" onClick={() => loadInventory(room)}>Inventory</Button></div></div>
    </Panel>)}</div>}

    {activeRoom && <Panel className="panel-pad" style={{ marginTop: 22 }}><SectionHeading title={`Nightly inventory · ${rooms.data?.find((r) => r.id === activeRoom)?.name ?? "Room"}`} detail="Set availability and price for a local calendar date." action={<Button variant="quiet" onClick={() => setActiveRoom(null)}>Close</Button>}/>
      <form onSubmit={saveInventory} className="form-grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", alignItems: "end" }}>
        <label className="label-control">Stay date<input className="input-control" type="date" value={date} onChange={(e) => setDate(e.target.value)}/></label>
        <label className="label-control">Room capacity<input className="input-control" type="number" min="0" max="10000" value={capacity} onChange={(e) => setCapacity(e.target.value)}/></label>
        <label className="label-control">Rooms available<input className="input-control" type="number" min="0" max="10000" value={available} onChange={(e) => setAvailable(e.target.value)}/></label>
        <label className="label-control">Nightly rate · INR<input className="input-control" type="number" min="0.01" step="0.01" value={rate} onChange={(e) => setRate(e.target.value)}/></label>
        <Button disabled={busy}>{busy ? "Saving…" : "Save date"}</Button>
      </form>
      <div className="table-wrap" style={{ marginTop: 18 }}><table className="data-table"><thead><tr><th>Date</th><th>Available</th><th>Nightly rate</th></tr></thead><tbody>{inventory.map((row) => <tr key={row.stay_date}><td>{formatDate(row.stay_date)}</td><td>{row.rooms_available} / {row.room_capacity}</td><td>{formatMoney(row.nightly_rate_inr)}</td></tr>)}</tbody></table></div>
    </Panel>}

    <SectionHeading title="Reservations" detail="Payment status comes from verified gateway webhook events." />
    {reservations.loading ? <Panel><Skeleton rows={5}/></Panel> : reservations.error ? <Panel><ErrorState message={reservations.error} onRetry={reservations.reload}/></Panel> : !reservations.data?.length ? <Panel><EmptyState title="No reservations yet" description="Customer hotel reservations will appear here after they are created."/></Panel> : <Panel className="table-wrap"><table className="data-table"><thead><tr><th>Guest</th><th>Room & dates</th><th>Guests</th><th>Total</th><th>Payment</th><th>Reservation</th></tr></thead><tbody>{reservations.data.map((booking) => <tr key={booking.id}><td><strong>{booking.customer_name || "Guest"}</strong><div className="table-secondary">{booking.customer_phone || booking.id.slice(0, 8)}</div></td><td>{booking.room_name}<div className="table-secondary">{formatDate(booking.check_in)} – {formatDate(booking.check_out)}</div></td><td>{booking.guests} · {booking.rooms} room(s)</td><td>{formatMoney(booking.amount_inr)}</td><td><StatePill value={booking.webhook_verified ? booking.payment_status || "verified" : "unverified"}/></td><td><StatePill value={booking.status}/></td></tr>)}</tbody></table></Panel>}

    {editing && <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && setEditing(null)}><div className="modal-card"><div className="modal-head"><div><h2>{editing === "new" ? "Add a room type" : `Edit ${editing.name}`}</h2><p>Customer totals are calculated from dated nightly inventory.</p></div><button className="close-button" onClick={() => setEditing(null)}><Icon name="close"/></button></div><form onSubmit={saveRoom}><div className="form-grid">
      <label className="label-control form-span-2">Room type name<input required minLength={2} maxLength={100} name="name" className="input-control" defaultValue={editing === "new" ? "" : editing.name}/></label>
      <label className="label-control">Maximum guests<input required type="number" min="1" max="12" name="max_guests" className="input-control" defaultValue={editing === "new" ? 2 : editing.max_guests}/></label>
      <label className="label-control">Base rate · INR/night<input required type="number" min="0.01" step="0.01" name="base_rate_inr" className="input-control" defaultValue={editing === "new" ? "" : editing.base_rate_inr}/></label>
      <label className="label-control">Total rooms<input required type="number" min="1" max="10000" name="total_rooms" className="input-control" defaultValue={editing === "new" ? 1 : editing.total_rooms}/></label>
      <label className="label-control">Free cancellation hours<input required type="number" min="0" max="720" name="free_cancellation_hours" className="input-control" defaultValue={editing === "new" ? 24 : editing.free_cancellation_hours}/></label>
      <label className="checkbox-line"><input name="is_active" type="checkbox" defaultChecked={editing === "new" ? true : editing.is_active}/> Available to drivers</label>
      <label className="label-control form-span-2">Description<textarea name="description" maxLength={2000} className="textarea-control" defaultValue={editing === "new" ? "" : editing.description ?? ""}/></label>
    </div><div className="form-actions"><Button type="button" variant="secondary" onClick={() => setEditing(null)}>Cancel</Button><Button disabled={busy}>{busy ? "Saving…" : "Save room type"}</Button></div></form></div></div>}
  </>;
}
