"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { apiGet } from "@/services/api";
import { useVendorAuth } from "@/components/vendor-auth";

const navigation = [
  ["/vendor/dashboard", "Overview", "grid"],
  ["/vendor/requests", "Requests", "inbox"],
  ["/vendor/bookings", "Bookings", "calendar"],
  ["/vendor/disputes", "Disputes", "shield"],
  ["/vendor/support", "Support tickets", "inbox"],
  ["/vendor/notifications", "Notifications", "bell"],
  ["/vendor/availability", "Availability", "clock"],
  ["/vendor/pricing", "Pricing", "tag"],
  ["/vendor/services", "Services", "bolt"],
  ["/vendor/hotels", "Hotel rooms", "hotel"],
  ["/vendor/restaurants", "Restaurant menu", "store"],
  ["/vendor/revenue", "Revenue", "chart"],
  ["/vendor/profile", "Business profile", "store"],
  ["/vendor/settings", "Settings", "settings"],
] as const;

const iconPaths: Record<string, string> = {
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M14 14h7v7h-7z M3 14h7v7H3z",
  inbox: "M4 4h16v13h-5l-3 3-3-3H4z M8 9h8 M8 12h5",
  calendar: "M4 5h16v15H4z M8 3v4 M16 3v4 M4 9h16 M8 13h3",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z M12 7v5l3 2",
  tag: "M20 13 13 20 3 10V4h6z M7 7h.01",
  bolt: "m13 2-9 12h7l-1 8 10-13h-7z",
  chart: "M4 19V5 M4 19h17 M7 15l4-4 3 2 6-7",
  store: "M3 10h18l-2-6H5z M5 10v10h14V10 M9 20v-6h6v6 M3 10c0 1 1 2 2 2s2-1 2-2c0 1 1 2 2 2s2-1 2-2c0 1 1 2 2 2s2-1 2-2c0 1 1 2 2 2s2-1 2-2",
  settings: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M19 13.5a7.4 7.4 0 0 0 0-3l2-1.5-2-3.5-2.3 1a8 8 0 0 0-2.5-1.5L14 2h-4l-.4 3a8 8 0 0 0-2.5 1.5l-2.3-1-2 3.5 2 1.5a7.4 7.4 0 0 0 0 3l-2 1.5 2 3.5 2.3-1a8 8 0 0 0 2.5 1.5L10 22h4l.4-3a8 8 0 0 0 2.5-1.5l2.3 1 2-3.5z",
  search: "M20 20l-4-4 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0z",
  arrow: "M5 12h14 M13 6l6 6-6 6",
  refresh: "M20 7v5h-5 M4 17v-5h5 M5.5 9A7 7 0 0 1 18 6l2 2 M4 16l2 2a7 7 0 0 0 12.5-3",
  close: "M6 6l12 12 M18 6 6 18",
  logout: "M10 17l5-5-5-5 M15 12H3 M12 3h7a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-7",
  check: "M5 12l4 4L19 6",
  pin: "M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0z M12 10h.01",
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M20 8v6 M23 11h-6",
  shield: "M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11z M9 12l2 2 4-4",
  list: "M9 6h12 M9 12h12 M9 18h12 M4 6h.01 M4 12h.01 M4 18h.01",
  bell: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9 M10 21h4",
  credit: "M2 6h20v12H2z M2 10h20 M6 15h4",
  wallet: "M3 5h17a1 1 0 0 1 1 1v13H3a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z M16 13h5 M4 4V3h14",
  hotel: "M3 21V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v16 M7 7h2 M15 7h2 M7 11h2 M15 11h2 M7 15h2 M15 15h2 M10 21v-4h4v4",
};

export function Icon({ name, size = 18, className = "" }: { name: string; size?: number; className?: string }) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className}><path d={iconPaths[name] ?? iconPaths.grid} /></svg>;
}

export function PortalShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut } = useVendorAuth();
  const [mobileNav, setMobileNav] = useState(false);
  const activeLabel = navigation.find(([href]) => pathname === href || (href !== "/vendor/dashboard" && pathname.startsWith(href)))?.[1] ?? "Overview";

  async function logout() {
    await signOut();
    router.replace("/login");
  }

  return <div className="portal-frame">
    <aside className="portal-sidebar">
      <Link className="brand-lockup" href="/vendor/dashboard" aria-label="VoltStop Vendor home">
        <span className="brand-symbol">V</span><span>VOLT<span className="brand-green">STOP</span><small>PARTNER PORTAL</small></span>
      </Link>
      <div className="sidebar-caption">WORKSPACE</div>
      <nav className="sidebar-nav" aria-label="Vendor workspace">
        {navigation.map(([href, label, icon]) => <Link key={href} href={href} className={`nav-link ${pathname === href || (href !== "/vendor/dashboard" && pathname.startsWith(href)) ? "nav-link-active" : ""}`}>
          <Icon name={icon} /><span>{label}</span>{href === "/vendor/requests" && <span className="nav-live-dot" />}
        </Link>)}
      </nav>
      <div className="sidebar-bottom"><div className="support-card"><span className="support-pulse"/><div><strong>NH-16 partner network</strong><span>Operations are live</span></div></div>
        <button className="nav-link sidebar-logout" onClick={logout}><Icon name="logout"/><span>Sign out</span></button>
      </div>
    </aside>
    <div className="portal-main">
      <header className="portal-topbar">
        <button className="mobile-menu-button" aria-label="Toggle navigation" onClick={() => setMobileNav((value) => !value)}><Icon name={mobileNav ? "close" : "grid"} /></button>
        <div className="breadcrumb">Workspace <span>/</span> <strong>{activeLabel}</strong></div>
        <div className="topbar-right"><span className="topbar-live"><i/> Network live</span><div className="topbar-divider"/><div className="account-chip"><span className="avatar-circle">{(user?.email?.[0] ?? user?.phone?.[0] ?? "V").toUpperCase()}</span><span className="account-email">{user?.email ?? user?.phone ?? "Vendor account"}</span></div></div>
      </header>
      {mobileNav && <nav className="mobile-nav" aria-label="Mobile vendor navigation">{navigation.map(([href,label,icon]) => <Link key={href} onClick={() => setMobileNav(false)} href={href}><Icon name={icon}/>{label}</Link>)}</nav>}
      <main className="portal-content">{children}</main>
      <footer className="portal-footer"><span>VoltStop partner operations</span><span>NH-16 · Srikakulam ↔ Vijayawada</span></footer>
    </div>
  </div>;
}

export function ProtectedPortal({ children }: { children: React.ReactNode }) {
  const { loading, user, configured } = useVendorAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, router, user]);
  if (loading || !user) return <FullPageLoading label={configured ? "Checking your session" : "Preparing partner workspace"}/>;
  return <PortalShell>{children}</PortalShell>;
}

export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: React.ReactNode }) {
  return <div className="page-heading"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <p className="page-description">{description}</p>}</div>{action && <div className="page-heading-action">{action}</div>}</div>;
}

export function Button({ children, variant = "primary", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "quiet" | "danger" }) {
  return <button {...props} className={`button button-${variant} ${props.className ?? ""}`}>{children}</button>;
}

export function Panel({ children, className = "", ...props }: React.HTMLAttributes<HTMLElement>) { return <section {...props} className={`panel ${className}`}>{children}</section>; }

export function SectionHeading({ title, detail, action }: { title: string; detail?: string; action?: React.ReactNode }) {
  return <div className="section-heading"><div><h2>{title}</h2>{detail && <p>{detail}</p>}</div>{action}</div>;
}

export function StatePill({ value }: { value: string }) {
  const key = value.toLowerCase().replaceAll("_", "-");
  return <span className={`state-pill state-${key}`}>{value.replaceAll("_", " ")}</span>;
}

export function Skeleton({ rows = 4 }: { rows?: number }) { return <div className="skeleton-stack" aria-label="Loading"><span className="skeleton-line skeleton-short"/>{Array.from({ length: rows }, (_, i) => <span key={i} className="skeleton-line"/>)}</div>; }

export function FullPageLoading({ label }: { label: string }) { return <div className="full-loading"><span className="spinner"/><span>{label}</span></div>; }

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="state-box"><span className="state-icon error-icon">!</span><h3>We couldn’t load this view</h3><p>{message}</p><Button variant="secondary" onClick={onRetry}><Icon name="refresh"/> Try again</Button></div>;
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: React.ReactNode }) {
  return <div className="state-box"><span className="state-icon"><Icon name="inbox" size={21}/></span><h3>{title}</h3><p>{description}</p>{action}</div>;
}

export function useVendorQuery<T>(path: string, token: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const reload = () => setVersion((value) => value + 1);
  useEffect(() => {
    if (!token || !path || (error && data === null)) return;
    const refreshWhenActive = () => {
      if (document.visibilityState === "visible" && navigator.onLine) setVersion((value) => value + 1);
    };
    const interval = window.setInterval(refreshWhenActive, 10_000);
    document.addEventListener("visibilitychange", refreshWhenActive);
    window.addEventListener("online", refreshWhenActive);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", refreshWhenActive);
      window.removeEventListener("online", refreshWhenActive);
    };
  }, [data, error, path, token]);
  useEffect(() => {
    let live = true;
    if (!token) { setData(null); setError(null); setLoading(false); return () => { live = false; }; }
    if (version === 0) setLoading(true);
    setError(null);
    apiGet<T>(path, token).then((result) => { if (live) setData(result); }).catch((reason: unknown) => {
      if (live) setError(reason instanceof Error ? reason.message : "Request failed.");
    }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [path, token, version]);
  return useMemo(() => ({ data, loading, error, reload, setData }), [data, error, loading, version]);
}

export function useAccessToken() {
  const { session } = useVendorAuth();
  return session?.access_token ?? null;
}

export function formatMoney(value: number | string | null | undefined) {
  const amount = Number(value ?? 0);
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number.isFinite(amount) ? amount : 0);
}

export function formatDate(value: string | Date, options: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }) {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat("en-IN", options).format(date);
}

export function formatTime(value: string | Date) { return formatDate(value, { hour: "numeric", minute: "2-digit", hour12: true }); }

export function toast(message: string) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("voltstop-toast", { detail: message }));
}

export function ToastViewport() {
  const [message, setMessage] = useState("");
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<string>).detail;
      setMessage(detail);
      window.setTimeout(() => setMessage((current) => current === detail ? "" : current), 3200);
    };
    window.addEventListener("voltstop-toast", handler);
    return () => window.removeEventListener("voltstop-toast", handler);
  }, []);
  return message ? <div role="status" className="toast-message"><span className="toast-check"><Icon name="check" size={15}/></span>{message}</div> : null;
}
