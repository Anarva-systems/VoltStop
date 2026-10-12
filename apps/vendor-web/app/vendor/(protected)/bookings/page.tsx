"use client";

import { PageHeader, useAccessToken } from "@/components/portal";
import { VendorBookingsTable } from "@/components/bookings-table";

export default function VendorBookingsPage() {
  const token = useAccessToken();
  return <><PageHeader eyebrow="RESERVATIONS" title="Bookings" description="Search your bookings, see the verified payment state and open a full reservation record."/><VendorBookingsTable token={token}/></>;
}
