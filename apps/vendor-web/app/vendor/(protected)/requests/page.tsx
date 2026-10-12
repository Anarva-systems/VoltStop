"use client";

import { PageHeader, useAccessToken } from "@/components/portal";
import { VendorBookingsTable } from "@/components/bookings-table";

export default function VendorRequestsPage() {
  const token = useAccessToken();
  return <><PageHeader eyebrow="BOOKING INBOX" title="Incoming requests" description="Review payment-confirmed bookings and acknowledge the reservations your team will serve."/><VendorBookingsTable token={token} onlyRequests/></>;
}
