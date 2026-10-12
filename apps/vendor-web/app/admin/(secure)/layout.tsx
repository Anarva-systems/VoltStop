import { AdminGuard } from "@/components/admin-portal";

export default function AdminProtectedLayout({ children }: { children: React.ReactNode }) {
  return <AdminGuard>{children}</AdminGuard>;
}
