import Link from "next/link";
import { AdminCard, AdminPage } from "@/components/admin-ui";

export default function RoutesPage() {
  return <><AdminPage title="Routes" description="Route records in VoltStop belong to customer trip planning, not an administrator-managed vendor route catalog."/><AdminCard title="Customer trip planning" subtitle="The API exposes POST /api/v1/routes/plan. It calculates an individual driver’s route and energy estimate; saved routes are private to that customer."><p>There is no platform route-management model, route assignment workflow, or administrator route CRUD endpoint. No unrelated route catalog has been added. Use <Link href="/admin/live-operations">Live Operations</Link> to inspect current service capacity and the existing route planner remains in the customer app.</p></AdminCard></>;
}
