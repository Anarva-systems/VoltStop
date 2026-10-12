"use client";

import { useEffect, useMemo, useState } from "react";
import { useVendorAuth } from "@/components/vendor-auth";
import { adminGet } from "@/services/admin-api";
import { Button, EmptyState, ErrorState, Icon, Skeleton, StatePill, ToastViewport } from "@/components/portal";

export function useAdminToken() { return useVendorAuth().session?.access_token ?? null; }
export function useAdminQuery<T>(path: string, token: string | null) {
  const [data, setData] = useState<T | null>(null); const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null); const [revision, setRevision] = useState(0);
  const reload = () => setRevision((value) => value + 1);
  useEffect(() => {
    if (!token || !path || (error && data === null)) return;
    const refreshWhenActive = () => {
      if (document.visibilityState === "visible" && navigator.onLine) setRevision((value) => value + 1);
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
    if (!token || !path) { setLoading(false); return; }
    let alive = true; if (revision === 0) setLoading(true); setError(null);
    adminGet<T>(path, token).then((result) => { if (alive) setData(result); }).catch((reason: unknown) => {
      if (alive) setError(reason instanceof Error ? reason.message : "Unable to load this information.");
    }).finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [path, revision, token]);
  return useMemo(() => ({ data, loading, error, reload, setData }), [data, error, loading, revision]);
}
export function AdminPage({ eyebrow = "PLATFORM OPERATIONS", title, description, action }: { eyebrow?: string; title: string; description?: string; action?: React.ReactNode }) {
  return <div className="admin-page-title"><div><p>{eyebrow}</p><h1>{title}</h1>{description && <span>{description}</span>}</div>{action && <div>{action}</div>}</div>;
}
export function AdminCard({ children, className = "", title, subtitle, action }: { children: React.ReactNode; className?: string; title?: string; subtitle?: string; action?: React.ReactNode }) {
  return <section className={`admin-card ${className}`}>{(title || action) && <header className="admin-card-head"><div>{title && <h2>{title}</h2>}{subtitle && <p>{subtitle}</p>}</div>{action}</header>}{children}</section>;
}
export function AdminLoad<T>({ loading, error, data, retry, children, empty, emptyTitle = "Nothing to show yet" }: { loading: boolean; error: string | null; data: T | null; retry: () => void; children: (value: T) => React.ReactNode; empty?: boolean; emptyTitle?: string }) {
  if (loading) return <AdminCard><Skeleton rows={5}/></AdminCard>;
  if (error) return <AdminCard><ErrorState message={error} onRetry={retry}/></AdminCard>;
  if (data === null || empty) return <AdminCard><EmptyState title={emptyTitle} description="This view updates when matching platform records are available."/></AdminCard>;
  return <>{children(data)}</>;
}
export function MetricCard({ label, value, note, icon, tone = "cyan" }: { label: string; value: string | number; note?: string; icon: string; tone?: "cyan" | "green" | "amber" | "red" }) {
  return <div className={`admin-metric metric-${tone}`}><div className="admin-metric-label">{label}<span><Icon name={icon}/></span></div><strong>{value}</strong>{note && <small>{note}</small>}</div>;
}
export function AdminTable({ headers, children, empty, emptyTitle }: { headers: string[]; children: React.ReactNode; empty?: boolean; emptyTitle?: string }) {
  return <div className="admin-table-wrap">{empty ? <EmptyState title={emptyTitle ?? "No matching records"} description="Try changing the filters or check back when more activity is recorded."/> : <table className="admin-table"><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{children}</tbody></table>}</div>;
}
export function FilterInput(props: React.InputHTMLAttributes<HTMLInputElement>) { return <input {...props} className={`admin-filter ${props.className ?? ""}`}/>; }
export function FilterSelect(props: React.SelectHTMLAttributes<HTMLSelectElement>) { return <select {...props} className={`admin-filter ${props.className ?? ""}`}/>; }
export function StateBadge({ value }: { value: string | null | undefined }) { return <StatePill value={value ?? "unknown"}/>; }
export function formatAdminMoney(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "Unavailable";
  const n = Number(value); return Number.isFinite(n) ? new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(n) : "Unavailable";
}
export function formatAdminDate(value: string | null | undefined, includeTime = false) {
  if (!value) return "—"; const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat("en-IN", includeTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" }).format(date);
}
export function AdminButton({ children, busy, variant = "primary", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { busy?: boolean; variant?: "primary" | "secondary" | "quiet" | "danger" }) {
  return <Button {...props} variant={variant} disabled={props.disabled || busy}>{busy && <span className="spinner spinner-small"/>}{children}</Button>;
}
export function AdminToastHost() { return <ToastViewport/>; }
export function AdminActionDialog({ title, description, impact, confirmLabel, busy, onClose, onConfirm }: {
  title: string; description: string; impact?: string; confirmLabel: string; busy?: boolean;
  onClose: () => void; onConfirm: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  return <div className="admin-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <form className="admin-modal" role="dialog" aria-modal="true" aria-labelledby="admin-action-title" onSubmit={(event) => { event.preventDefault(); void onConfirm(reason); }}>
      <div className="admin-modal-head"><h2 id="admin-action-title">{title}</h2><button type="button" className="admin-modal-close" aria-label="Close" onClick={onClose}>×</button></div>
      <p>{description}</p>{impact && <div className="admin-note">{impact}</div>}
      <label className="admin-reason">Reason (required)<textarea className="admin-filter" minLength={8} maxLength={1000} required value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Document the operational reason"/></label>
      <div className="admin-modal-actions"><Button type="button" variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button><Button type="submit" variant="danger" disabled={busy || reason.trim().length < 8}>{busy ? "Working…" : confirmLabel}</Button></div>
    </form>
  </div>;
}
