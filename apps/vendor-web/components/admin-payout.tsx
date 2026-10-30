"use client";

import { FormEvent, useState } from "react";
import { adminPost } from "@/services/admin-api";
import { kycValidationError, payoutRoutingValidationError, PLATFORM_RETENTION_FLOOR_BPS, MAX_COMMISSION_RATE_BPS } from "@/services/payout-view";
import { toast } from "@/components/portal";
import { AdminButton, AdminCard, AdminLoad, AdminTable, StateBadge, formatAdminDate, formatAdminMoney, useAdminQuery, useAdminToken } from "@/components/admin-ui";
import type { PayoutTransfer } from "@/types/vendor";

export type VendorPayoutView = {
  payouts_enabled: boolean;
  razorpay_linked_account_id: string | null;
  commission_rate_bps_override: number | null;
  kyc_status: string | null;
  kyc_reference: string | null;
  kyc_gstin: string | null;
  kyc_pan_masked: string | null;
  bank_account_masked: string | null;
  kyc_verified_at: string | null;
  verification_status: string;
};

// The admin ledger widens the vendor-facing row with the business name, and reports the
// planned/provider-event timestamps because only a verified event advances a row past planned.
type AdminTransferRow = PayoutTransfer & { vendor_id: string; vendor_name: string };
type TransferPage = { items: AdminTransferRow[]; limit: number; offset: number };

const KYC_STATUSES = ["not_started", "submitted", "under_review", "verified", "rejected"];

export function TransferLedger({ path }: { path: string }) {
  const token = useAdminToken();
  const transfers = useAdminQuery<TransferPage>(path, token);
  return <AdminLoad loading={transfers.loading} error={transfers.error} data={transfers.data} retry={transfers.reload}
    empty={Boolean(transfers.data && !transfers.data.items.length)} emptyTitle="No transfer rows yet">
    {(data) => <AdminTable headers={["Vendor", "Source", "Booked amount", "Vendor share", "Commission", "Rate", "State", "Provider reference", "Timing"]}>
      {data.items.map((row) => <tr key={row.id}>
        <td className="primary-cell">{row.vendor_name}</td>
        <td>{row.source_kind.replaceAll("_", " ")}</td>
        <td>{formatAdminMoney(row.gross_amount_inr)}</td>
        <td>{formatAdminMoney(row.vendor_amount_inr)}</td>
        <td>{formatAdminMoney(row.commission_inr)}</td>
        <td>{row.rate_bps / 100}%</td>
        <td><StateBadge value={row.status}/>{row.failure_reason ? <small style={{ display: "block" }}>{row.failure_reason}</small> : null}</td>
        <td>{row.razorpay_transfer_id ?? row.settlement_utr ?? row.razorpay_order_id ?? "—"}</td>
        <td>{formatAdminDate(row.planned_at, true)}<small style={{ display: "block" }}>{row.provider_event_at ? `Confirmed ${formatAdminDate(row.provider_event_at, true)}` : "Awaiting provider event"}</small></td>
      </tr>)}
    </AdminTable>}
  </AdminLoad>;
}

export function AdminVendorPayout({ vendorId, vendor, canManageRouting, canReviewKyc, canReadTransfers, onChanged }: {
  vendorId: string;
  vendor: VendorPayoutView;
  canManageRouting: boolean;
  canReviewKyc: boolean;
  canReadTransfers: boolean;
  onChanged: () => void;
}) {
  const token = useAdminToken();
  const [account, setAccount] = useState(vendor.razorpay_linked_account_id ?? "");
  const [rate, setRate] = useState(vendor.commission_rate_bps_override?.toString() ?? "");
  const [enabled, setEnabled] = useState(vendor.payouts_enabled);
  const [routingReason, setRoutingReason] = useState("");
  const [routingBusy, setRoutingBusy] = useState(false);
  const [routingError, setRoutingError] = useState("");

  const [kycStatus, setKycStatus] = useState(vendor.kyc_status && KYC_STATUSES.includes(vendor.kyc_status) ? vendor.kyc_status : "submitted");
  const [kycForm, setKycForm] = useState({
    kyc_pan_masked: vendor.kyc_pan_masked ?? "",
    bank_account_masked: vendor.bank_account_masked ?? "",
    kyc_gstin: vendor.kyc_gstin ?? "",
    kyc_reference: vendor.kyc_reference ?? "",
  });
  const [kycReason, setKycReason] = useState("");
  const [kycBusy, setKycBusy] = useState(false);
  const [kycError, setKycError] = useState("");

  async function saveRouting(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const trimmedAccount = account.trim();
    const trimmedRate = rate.trim();
    const invalid = payoutRoutingValidationError({
      linked_account_id: trimmedAccount,
      commission_rate_bps: trimmedRate,
      reason: routingReason,
      payouts_enabled: enabled,
      account_on_file: Boolean(vendor.razorpay_linked_account_id),
    });
    if (invalid) { setRoutingError(invalid); return; }
    setRoutingError("");
    setRoutingBusy(true);
    try {
      await adminPost(`/vendors/${vendorId}/payout-routing`, token, {
        ...(trimmedAccount ? { razorpay_linked_account_id: trimmedAccount } : {}),
        payouts_enabled: enabled,
        commission_rate_bps_override: trimmedRate ? Number(trimmedRate) : null,
        reason: routingReason.trim(),
      });
      setRoutingReason("");
      toast("Payout routing updated");
      onChanged();
    } catch (reason) {
      setRoutingError(reason instanceof Error ? reason.message : "Payout routing was not updated");
    } finally { setRoutingBusy(false); }
  }

  async function saveKyc(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    if (kycStatus === "verified") {
      if (kycReason.trim().length < 8) { setKycError("Record what you checked before verifying (at least 8 characters)."); return; }
      const missing = !kycForm.kyc_pan_masked || !kycForm.bank_account_masked;
      if (missing) { setKycError("Verification needs the masked PAN and the masked bank account on record."); return; }
    }
    if (kycForm.kyc_pan_masked || kycForm.bank_account_masked || kycForm.kyc_gstin) {
      const invalid = kycValidationError(kycForm);
      if (invalid) { setKycError(invalid); return; }
    }
    setKycError("");
    setKycBusy(true);
    try {
      await adminPost(`/vendors/${vendorId}/kyc`, token, {
        status: kycStatus,
        kyc_reference: kycForm.kyc_reference.trim() || null,
        kyc_gstin: kycForm.kyc_gstin.trim() || null,
        kyc_pan_masked: kycForm.kyc_pan_masked.trim() || null,
        bank_account_masked: kycForm.bank_account_masked.trim() || null,
        ...(kycReason.trim() ? { reason: kycReason.trim() } : {}),
      });
      setKycReason("");
      toast(`KYC marked ${kycStatus.replaceAll("_", " ")}`);
      onChanged();
    } catch (reason) {
      setKycError(reason instanceof Error ? reason.message : "KYC review was not saved");
    } finally { setKycBusy(false); }
  }

  return <div className="admin-stack">
    <AdminCard title="Payout routing" subtitle="Razorpay Route splits captured payments toward this vendor's own account.">
      <div className="admin-detail-grid">
        <div className="admin-detail-item"><small>Routing switch</small><strong>{vendor.payouts_enabled ? "Enabled" : "Disabled"}</strong></div>
        <div className="admin-detail-item"><small>Linked account</small><strong>{vendor.razorpay_linked_account_id ?? "Not linked"}</strong></div>
        <div className="admin-detail-item"><small>Commission override</small><strong>{vendor.commission_rate_bps_override === null ? "Platform rate" : `${vendor.commission_rate_bps_override / 100}%`}</strong></div>
        <div className="admin-detail-item"><small>KYC state</small><strong>{vendor.kyc_status?.replaceAll("_", " ") ?? "not_started"}</strong></div>
      </div>
      {!canManageRouting
        ? <div className="admin-callout" style={{ marginTop: 12 }}>Your admin role has no payouts:manage permission, so routing settings are read only.</div>
        : <form onSubmit={saveRouting}>
            {routingError && <p className="form-error" role="alert">{routingError}</p>}
            <div className="admin-form-grid">
              <label>Razorpay linked account<input className="admin-filter" value={account} maxLength={64}
                placeholder="acc_1a2b3c4d" onChange={(event) => setAccount(event.target.value)}/></label>
              <label>Commission override · bps<input className="admin-filter" type="number" min={PLATFORM_RETENTION_FLOOR_BPS} max={MAX_COMMISSION_RATE_BPS} step="1"
                value={rate} placeholder="Blank uses the platform rate" onChange={(event) => setRate(event.target.value)}/></label>
              <label>Routing switch<select className="admin-filter" value={enabled ? "enabled" : "disabled"}
                onChange={(event) => setEnabled(event.target.value === "enabled")}><option value="disabled">Disabled</option><option value="enabled">Enabled</option></select></label>
              <label>Reason (required)<input className="admin-filter" value={routingReason} maxLength={1000}
                placeholder="For example: provider account checked against the KYC record"
                onChange={(event) => setRoutingReason(event.target.value)}/></label>
            </div>
            <div className="admin-note" style={{ marginTop: 12 }}>Enabling routing does not move money by itself: transfers are created only when a captured payment is split, and only a verified provider event marks a row as processed or settled.</div>
            <div className="admin-actions"><AdminButton busy={routingBusy}>Save routing</AdminButton></div>
          </form>}
    </AdminCard>

    <AdminCard title="KYC review" subtitle="Only masked identifiers are stored here; full PAN, IFSC and account numbers stay with the provider.">
      {!canReviewKyc
        ? <div className="admin-callout">Your admin role has no vendor_onboarding:manage permission, so KYC decisions are read only.</div>
        : <form onSubmit={saveKyc}>
            {kycError && <p className="form-error" role="alert">{kycError}</p>}
            <div className="admin-form-grid">
              <label>KYC status<select className="admin-filter" value={kycStatus} onChange={(event) => setKycStatus(event.target.value)}>
                {KYC_STATUSES.map((status) => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}</select></label>
              <label>Masked PAN<input className="admin-filter" value={kycForm.kyc_pan_masked} maxLength={10} placeholder="ABCDE****F"
                onChange={(event) => setKycForm({ ...kycForm, kyc_pan_masked: event.target.value.toUpperCase() })}/></label>
              <label>Masked bank account<input className="admin-filter" value={kycForm.bank_account_masked} maxLength={18} placeholder="*****1234"
                onChange={(event) => setKycForm({ ...kycForm, bank_account_masked: event.target.value })}/></label>
              <label>GSTIN<input className="admin-filter" value={kycForm.kyc_gstin} maxLength={15} placeholder="29ABCDE1234F1Z5"
                onChange={(event) => setKycForm({ ...kycForm, kyc_gstin: event.target.value.toUpperCase() })}/></label>
              <label>Provider reference<input className="admin-filter" value={kycForm.kyc_reference} maxLength={120} placeholder="Razorpay KYC reference"
                onChange={(event) => setKycForm({ ...kycForm, kyc_reference: event.target.value })}/></label>
              <label>Decision reason<input className="admin-filter" value={kycReason} maxLength={1000} placeholder="What was checked"
                onChange={(event) => setKycReason(event.target.value)}/></label>
            </div>
            <div className="admin-actions"><AdminButton busy={kycBusy}>Save KYC decision</AdminButton></div>
          </form>}
      <div className="admin-detail-grid" style={{ marginTop: 14 }}>
        <div className="admin-detail-item"><small>Masked PAN</small><strong>{vendor.kyc_pan_masked ?? "Not on record"}</strong></div>
        <div className="admin-detail-item"><small>Masked bank account</small><strong>{vendor.bank_account_masked ?? "Not on record"}</strong></div>
        <div className="admin-detail-item"><small>GSTIN</small><strong>{vendor.kyc_gstin ?? "Not provided"}</strong></div>
        <div className="admin-detail-item"><small>Provider reference</small><strong>{vendor.kyc_reference ?? "Not provided"}</strong></div>
        <div className="admin-detail-item"><small>Verified on</small><strong>{vendor.kyc_verified_at ? formatAdminDate(vendor.kyc_verified_at, true) : "Not verified"}</strong></div>
        <div className="admin-detail-item"><small>Vendor approval</small><strong>{vendor.verification_status.replaceAll("_", " ")}</strong></div>
      </div>
    </AdminCard>

    {canReadTransfers ? <AdminCard title="Transfer ledger for this vendor" subtitle="Charging, hotel and restaurant transfers share one ledger.">
      <TransferLedger path={`/payout-transfers?vendor_id=${vendorId}&limit=50`}/>
    </AdminCard> : <div className="admin-callout">Your admin role has no payouts:read permission, so the transfer ledger for this business is hidden.</div>}
  </div>;
}
