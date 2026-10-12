"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useVendorAuth } from "@/components/vendor-auth";
import { adminGet } from "@/services/admin-api";
import { Button, FullPageLoading, Icon } from "@/components/portal";
import { AdminToastHost } from "@/components/admin-ui";

type AdminIdentity = { user_id: string; email: string | null; role: string; permissions: string[] };
const groups = [
  { label: "OVERVIEW", items: [["/admin", "Overview", "grid"]] },
  { label: "OPERATIONS", items: [["/admin/bookings", "Bookings", "calendar"], ["/admin/restaurant-orders", "Restaurant Orders", "store"], ["/admin/live-operations", "Live Operations", "pin"], ["/admin/vendors", "Vendors", "store"], ["/admin/vendor-onboarding", "Vendor Onboarding", "check"]] },
  { label: "FINANCE", items: [["/admin/transactions", "Transactions", "credit"], ["/admin/payouts", "Payouts", "wallet"], ["/admin/refunds", "Refunds", "refresh"], ["/admin/hotel-refunds", "Hotel refunds", "hotel"]] },
  { label: "RISK & SUPPORT", items: [["/admin/complaints", "Complaints & disputes", "shield"], ["/admin/support", "Support tickets", "inbox"]] },
  { label: "SYSTEM", items: [["/admin/admin-users", "Admin Users", "users"], ["/admin/roles", "Roles & Permissions", "settings"], ["/admin/audit-logs", "Audit Logs", "list"], ["/admin/analytics", "Analytics", "chart"]] },
] as const;
const names: Record<string, string> = {
  "/admin": "Overview", "/admin/vendors": "Vendor Management", "/admin/vendor-onboarding": "Vendor Onboarding",
  "/admin/bookings": "Booking Monitor", "/admin/restaurant-orders": "Restaurant Order Monitor", "/admin/live-operations": "Live Operations", "/admin/transactions": "Transactions",
  "/admin/payouts": "Payouts", "/admin/refunds": "Refunds", "/admin/hotel-refunds": "Hotel refunds", "/admin/disputes": "Disputes",
  "/admin/analytics": "Analytics", "/admin/audit-logs": "Audit Logs", "/admin/admin-users": "Admin Users", "/admin/roles": "Roles & Permissions",
  "/admin/customers": "Customers", "/admin/availability": "Availability", "/admin/complaints": "Complaints & disputes",
  "/admin/support": "Support tickets", "/admin/routes": "Routes", "/admin/services": "Services",
  "/admin/pricing": "Pricing rules", "/admin/notifications": "Notifications", "/admin/settings": "Settings",
};

export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { loading, user, session, signOut } = useVendorAuth();
  const [identity, setIdentity] = useState<AdminIdentity | null>(null);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  useEffect(() => {
    if (loading) return;
    if (!user || !session?.access_token) { router.replace("/login"); return; }
    let active = true;
    setChecking(true);
    adminGet<AdminIdentity>("/me", session.access_token).then((value) => {
      if (active) { setIdentity(value); setError(null); }
    }).catch((reason: unknown) => {
      if (!active) return;
      const value = reason instanceof Error ? reason : new Error("Administrator access could not be verified.");
      if ((value as Error & { status?: number }).status === 401) router.replace("/login");
      else setError(value.message);
    }).finally(() => active && setChecking(false));
    return () => { active = false; };
  }, [loading, router, session?.access_token, user]);
  if (loading || checking) return <FullPageLoading label="Verifying administrator access"/>;
  if (!user) return <FullPageLoading label="Opening administrator sign in"/>;
  if (error || !identity) return <div className="admin-denied"><Icon name="shield" size={28}/><h1>Admin access unavailable</h1><p>{error ?? "This account is not authorized for the internal operations console."}</p><Button onClick={async () => { await signOut(); router.replace("/admin/login"); }}>Sign out</Button></div>;
  return <AdminShell identity={identity}>{children}</AdminShell>;
}

function AdminShell({ identity, children }: { identity: AdminIdentity; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { signOut } = useVendorAuth();
  const [navOpen, setNavOpen] = useState(false);
  const [search, setSearch] = useState("");
  const title = names[pathname] ?? (pathname.startsWith("/admin/vendors/") ? "Vendor Detail" : pathname.startsWith("/admin/disputes/") ? "Dispute Detail" : "Operations");
  const env = process.env.NEXT_PUBLIC_APP_ENV ?? "Development";
  const initials = useMemo(() => (identity.email?.split("@")[0] ?? "A").slice(0, 2).toUpperCase(), [identity.email]);
  function globalSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const term = search.trim();
    if (term) router.push(`/admin/bookings?search=${encodeURIComponent(term)}`);
  }
  async function logout() { await signOut(); router.replace("/login"); }
  return <div className="admin-frame">
    {navOpen && <button aria-label="Close navigation" className="admin-scrim" onClick={() => setNavOpen(false)}/>}
    <aside className={`admin-sidebar ${navOpen ? "admin-sidebar-open" : ""}`}>
      <Link href="/admin" className="admin-brand"><span className="admin-brand-mark">V</span><span>VOLT<span>STOP</span><small>OPERATIONS CONSOLE</small></span></Link>
      <div className="admin-nav-scroll">
        {groups.map((group) => <section className="admin-nav-group" key={group.label}><h2>{group.label}</h2>{group.items.map(([href,label,icon]) => <Link key={href} href={href} onClick={() => setNavOpen(false)} className={`admin-nav-link ${pathname === href || (href !== "/admin" && pathname.startsWith(`${href}/`)) ? "active" : ""}`}><Icon name={icon} size={17}/><span>{label}</span></Link>)}</section>)}
        <section className="admin-nav-group"><h2>OPERATIONS · MORE</h2>{[["/admin/customers","Customers","users"],["/admin/availability","Availability","clock"]].map(([href,label,icon])=><Link key={href} href={href} onClick={()=>setNavOpen(false)} className={`admin-nav-link ${pathname===href?"active":""}`}><Icon name={icon} size={17}/><span>{label}</span></Link>)}</section>
        <section className="admin-nav-group"><h2>PLATFORM</h2>{[["/admin/routes","Routes","pin"],["/admin/services","Services","bolt"],["/admin/pricing","Pricing Rules","tag"],["/admin/notifications","Notifications","bell"]].map(([href,label,icon])=><Link key={href} href={href} onClick={()=>setNavOpen(false)} className={`admin-nav-link ${pathname===href?"active":""}`}><Icon name={icon} size={17}/><span>{label}</span></Link>)}</section>
        <section className="admin-nav-group"><h2>SYSTEM</h2>{[["/admin/settings","Settings","settings"]].map(([href,label,icon])=><Link key={href} href={href} onClick={()=>setNavOpen(false)} className={`admin-nav-link ${pathname===href?"active":""}`}><Icon name={icon} size={17}/><span>{label}</span></Link>)}</section>
      </div>
      <div className="admin-sidebar-footer"><span className="admin-env-dot"/><div><strong>Platform API</strong><small>Authenticated · {env}</small></div></div>
    </aside>
    <div className="admin-main"><header className="admin-topbar"><button className="admin-menu" aria-label="Open menu" onClick={() => setNavOpen(true)}><Icon name="grid"/></button><div className="admin-crumb">VoltStop <span>/</span> <strong>{title}</strong></div>
      <div className="admin-header-tools"><form className="admin-global-search" onSubmit={globalSearch}><Icon name="search" size={16}/><input aria-label="Search bookings" placeholder="Search bookings or customers" value={search} onChange={(event) => setSearch(event.target.value)}/><kbd>↵</kbd></form><span className="admin-role-chip">{identity.role.replaceAll("_", " ")}</span><div className="admin-profile"><span>{initials}</span><div><strong>{identity.email ?? "Administrator"}</strong><small>{identity.role.replaceAll("_", " ")}</small></div></div><button className="admin-logout" onClick={logout} aria-label="Sign out"><Icon name="logout" size={17}/></button></div>
    </header><main className="admin-content">{children}</main><footer className="admin-footer"><span>VoltStop internal operations</span><span>Administrative actions are recorded</span></footer><AdminToastHost/></div>
  </div>;
}
