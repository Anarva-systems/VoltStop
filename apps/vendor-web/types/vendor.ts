export type VendorProfile = {
  id: string;
  name: string;
  type: "restaurant" | "hotel";
  phone: string | null;
  address: string;
  lat: number;
  lng: number;
  description: string | null;
  image_url: string | null;
  operating_hours: string | null;
  is_active: boolean;
  is_verified: boolean;
  verification_status?: "pending" | "under_review" | "changes_requested" | "approved" | "rejected" | "suspended";
  decision_reason?: string | null;
  services?: VendorService[];
};

export type VendorService = {
  id: string;
  service_type: string;
  display_name: string | null;
  description: string | null;
  price_inr: number;
  capacity: number | null;
  availability: Record<string, unknown>;
  is_active: boolean;
};

export type VendorSlot = {
  id: string;
  vendor_id: string;
  slot_start_time: string;
  slot_end_time: string;
  capacity: number;
  price_inr: number;
  status: "available" | "locked" | "booked" | "closed";
  service_type: string;
  active_bookings: number;
  booking_history: number;
  locked?: boolean;
};

export type VendorBooking = {
  booking_id: string;
  status: "pending" | "confirmed" | "cancelled" | "completed" | "expired";
  vendor_acknowledgement: "pending" | "accepted";
  amount_inr: number;
  created_at: string;
  payment_status: string | null;
  charged_amount_inr?: number;
  webhook_verified?: boolean;
  slot_id: string;
  slot_start_time: string;
  slot_end_time: string;
  capacity: number;
  service_type: string;
  customer_name: string;
  customer_phone?: string;
  ev_model?: string | null;
  battery_kwh?: number | null;
  service_name: string;
  vendor_id?: string;
  vendor_name?: string;
  customer_id?: string;
  currency?: string;
  updated_at?: string;
  timeline?: { event_type: string; created_at: string; metadata: Record<string, unknown> }[];
};

type DashboardBooking = Pick<VendorBooking, "booking_id" | "status" | "slot_start_time" | "slot_end_time" | "service_type" | "payment_status" | "webhook_verified" | "customer_name" | "amount_inr" | "vendor_acknowledgement">;

export type VendorDashboard = {
  metrics: {
    pending_requests: number;
    todays_bookings: number;
    available_capacity: number;
    todays_revenue: number;
  };
  schedule: DashboardBooking[];
  requests: DashboardBooking[];
  activity: { id: string; event_type: string; created_at: string; booking_id: string; metadata: Record<string, unknown> }[];
};

export type RevenueReport = {
  today_gross: number;
  week_gross: number;
  month_gross: number;
  all_time_gross: number;
  completed_refunds: number;
  platform_fee: number;
  estimated_payout: number;
  commission_rate_bps: number;
  total_bookings: number;
  completed_bookings: number;
  cancelled_bookings: number;
  captured_payments: number;
  refunded_payments: number;
};
