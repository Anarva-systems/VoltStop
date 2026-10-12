"use client";

import { useEffect, useMemo, useState } from "react";
import L from "leaflet";
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";

export type SelectedLocation = { lat: number; lng: number };

const markerIcon = L.divIcon({
  className: "voltstop-map-marker",
  html: '<span aria-hidden="true"></span>',
  iconSize: [28, 36],
  iconAnchor: [14, 34],
});
const tileUrl = process.env.NEXT_PUBLIC_OSM_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

function MapActions({ focus, onPick }: { focus: SelectedLocation | null; onPick?: (point: SelectedLocation) => void }) {
  const map = useMap();
  useEffect(() => {
    if (focus) map.flyTo([focus.lat, focus.lng], Math.max(map.getZoom(), 14), { duration: 0.35 });
  }, [focus, map]);
  useMapEvents({ click: ({ latlng }) => onPick?.({ lat: latlng.lat, lng: latlng.lng }) });
  return null;
}

export default function LocationPicker({
  initialValue,
  onConfirm,
  readOnly = false,
}: {
  initialValue: SelectedLocation | null;
  onConfirm?: (location: SelectedLocation) => void;
  readOnly?: boolean;
}) {
  const [pending, setPending] = useState<SelectedLocation | null>(initialValue);
  const [focus, setFocus] = useState<SelectedLocation | null>(initialValue);
  const [message, setMessage] = useState("");
  const center = useMemo<[number, number]>(() => initialValue ? [initialValue.lat, initialValue.lng] : [20.5937, 78.9629], []);

  function useCurrentLocation() {
    setMessage("");
    if (!navigator.geolocation) {
      setMessage("Location access is not available in this browser. You can still choose a point on the map.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const point = { lat: coords.latitude, lng: coords.longitude };
        setPending(point);
        setFocus(point);
      },
      (error) => setMessage(error.code === error.PERMISSION_DENIED
        ? "Location permission was denied. Choose a point on the map instead."
        : "Your current location could not be found. Choose a point on the map instead."),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    );
  }

  const marker = pending ?? focus;
  return <div className="location-picker">
    {!readOnly && <div className="location-picker-toolbar">
      <p>Choose the pin location. Tap the map or drag the marker to refine it.</p>
      <button type="button" className="button button-secondary" onClick={useCurrentLocation}>Use current location</button>
    </div>}
    <div className="location-map" aria-label="Map for selecting the business location">
      <MapContainer center={center} zoom={initialValue ? 14 : 4} scrollWheelZoom className="location-map-canvas">
        <TileLayer
          url={tileUrl}
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>'
        />
        <MapActions focus={focus} onPick={readOnly ? undefined : (point) => { setPending(point); setFocus(null); }} />
        {marker && <Marker
          position={[marker.lat, marker.lng]}
          icon={markerIcon}
          draggable={!readOnly}
          eventHandlers={{ dragend: (event) => {
            const point = event.target.getLatLng();
            setPending({ lat: point.lat, lng: point.lng });
          } }}
        />}
      </MapContainer>
    </div>
    {!readOnly && <div className="location-picker-footer">
      <span aria-live="polite">{message || (pending ? `Selected point · ${pending.lat.toFixed(5)}, ${pending.lng.toFixed(5)}` : "No location selected yet")}</span>
      <button type="button" className="button button-primary" disabled={!pending} onClick={() => pending && onConfirm?.(pending)}>Use this location</button>
    </div>}
  </div>;
}
