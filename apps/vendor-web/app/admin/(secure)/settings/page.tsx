"use client";

import Link from "next/link";
import { AdminCard, AdminLoad, AdminPage, useAdminQuery, useAdminToken } from "@/components/admin-ui";

type Settings = {
  portal_origin: string;
  database?: { configured: boolean };
  redis?: { configured: boolean };
  payment?: {
    provider: string;
    public_key_configured: boolean;
    server_secret_configured: boolean;
    webhook_secret_configured: boolean;
    mode: string;
    checkout_ready: boolean;
  };
  commission?: {
    settings_configured: boolean;
    ledger_configured: boolean;
    capture_trigger_configured: boolean;
    rate_bps: number | null;
    scope: string;
  };
  vendor_settlement?: {
    provider: string | null;
    configured: boolean;
    ledger_configured: boolean;
    automatic_transfers_enabled: boolean;
    status: string;
    reason: string;
  };
  geocoding?: { enabled: boolean; reason: string };
  editable_platform_config: boolean;
};

const presence = (configured?: boolean) => configured === undefined
  ? "Not reported by API"
  : configured ? "Configured" : "Missing";

export default function SettingsPage() {
  const token = useAdminToken();
  const query = useAdminQuery<Settings>("/settings", token);

  return <>
    <AdminPage
      title="Platform settings"
      description="Live configuration checks for the API environment. Secret values are never returned."
    />
    <AdminLoad loading={query.loading} error={query.error} data={query.data} retry={query.reload}>
      {(data) => <div className="admin-grid-2">
        <AdminCard title="API and infrastructure">
          <dl className="admin-settings-list">
            <dt>Vendor portal origin</dt><dd>{data.portal_origin}</dd>
            <dt>Database connection</dt><dd>{presence(data.database?.configured)}</dd>
            <dt>Redis booking locks</dt><dd>{presence(data.redis?.configured)}</dd>
            <dt>Platform settings</dt>
            <dd>{data.editable_platform_config ? "Editable" : "Environment-managed"}</dd>
          </dl>
        </AdminCard>

        <AdminCard title="Customer payment collection">
          <dl className="admin-settings-list">
            <dt>Provider</dt><dd>{data.payment?.provider ?? "Not reported by API"}</dd>
            <dt>Environment</dt><dd>{!data.payment?.mode || data.payment.mode === "unconfigured" ? "Not configured" : data.payment.mode}</dd>
            <dt>Checkout key</dt><dd>{presence(data.payment?.public_key_configured ?? false)}</dd>
            <dt>Server credential</dt><dd>{presence(data.payment?.server_secret_configured ?? false)}</dd>
            <dt>Webhook verification</dt><dd>{presence(data.payment?.webhook_secret_configured ?? false)}</dd>
            <dt>Collection status</dt><dd>{data.payment?.checkout_ready ? "Ready for provider checkout" : "Unavailable or not reported"}</dd>
          </dl>
          <p className="admin-note">
            {data.payment?.checkout_ready
              ? "The API has the credentials needed to create checkout orders and verify provider webhooks. A production launch still requires an HTTPS API and a verified provider webhook URL."
              : "Razorpay checkout cannot process payments in this environment until the API host has its key ID, server secret, and webhook secret configured."}
          </p>
        </AdminCard>

        <AdminCard title="Commission policy">
          <dl className="admin-settings-list">
            <dt>Commission policy</dt>
            <dd>{data.commission?.settings_configured && data.commission.rate_bps !== null
              ? `${data.commission.rate_bps / 100}% on new verified charging bookings`
              : data.commission ? "Not configured in the connected database" : "Not reported by API"}</dd>
            <dt>Payment commission ledger</dt><dd>{presence(data.commission?.ledger_configured)}</dd>
            <dt>Capture recording trigger</dt><dd>{presence(data.commission?.capture_trigger_configured)}</dd>
            <dt>Applies to</dt><dd>Charging bookings</dd>
          </dl>
          <p className="admin-note">Only server-verified captured payments create commission records. The policy does not itself move money to or from a vendor.</p>
        </AdminCard>

        <AdminCard title="Vendor settlements">
          <dl className="admin-settings-list">
            <dt>Transfer provider</dt><dd>{data.vendor_settlement?.provider ?? "Not connected"}</dd>
            <dt>Payout ledger</dt><dd>{presence(data.vendor_settlement?.ledger_configured)}</dd>
            <dt>Automatic transfers</dt><dd>{data.vendor_settlement?.automatic_transfers_enabled ? "Enabled" : "Not implemented"}</dd>
            <dt>Current state</dt><dd>Estimate only</dd>
          </dl>
          <p className="admin-note">{data.vendor_settlement?.reason ?? "The running API does not report a vendor settlement provider or payout ledger."} Vendor balances on the finance pages are not marked paid and no transfer is initiated.</p>
        </AdminCard>

        <AdminCard title="External services">
          <dl className="admin-settings-list">
            <dt>Address geocoding</dt><dd>{data.geocoding?.enabled ? "Enabled" : "Disabled"}</dd>
            <dt>Reason</dt><dd>{data.geocoding?.reason ?? "No geocoding status reported"}</dd>
          </dl>
        </AdminCard>

        <AdminCard title="Access management">
          <p>Role assignments and server-enforced permissions are managed separately.</p>
          <Link className="action-link" href="/admin/admin-users">Manage administrator access →</Link>
          {" · "}
          <Link className="action-link" href="/admin/roles">Review role grants →</Link>
        </AdminCard>
      </div>}
    </AdminLoad>
  </>;
}
