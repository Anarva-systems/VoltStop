"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiPost } from "@/services/api";
import {
  commissionRateLabel,
  formatRupees,
  kycValidationError,
  maskAccountId,
  payoutRoutingCopy,
  payoutRoutingPill,
  transferStatusLabel,
} from "@/services/payout-view";
import {
  Button,
  EmptyState,
  ErrorState,
  Icon,
  Panel,
  SectionHeading,
  Skeleton,
  StatePill,
  toast,
  useVendorQuery,
} from "@/components/portal";
import type { PayoutStatus, PayoutTransferPage } from "@/types/vendor";

export function PayoutPanel({ token }: { token: string | null }) {
  const status = useVendorQuery<PayoutStatus>("/payout-status", token);
  const transfers = useVendorQuery<PayoutTransferPage>("/payout-transfers?limit=25", token);
  const [form, setForm] = useState({ kyc_pan_masked: "", bank_account_masked: "", kyc_gstin: "", kyc_reference: "" });
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    const kyc = status.data?.kyc;
    if (!kyc) return;
    setForm({
      kyc_pan_masked: kyc.pan_masked ?? "",
      bank_account_masked: kyc.bank_account_masked ?? "",
      kyc_gstin: kyc.gstin ?? "",
      kyc_reference: kyc.reference ?? "",
    });
  }, [status.data]);

  async function submitKyc(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const invalid = kycValidationError(form);
    if (invalid) { setFormError(invalid); return; }
    setFormError("");
    setBusy(true);
    try {
      await apiPost("/kyc", token, {
        kyc_pan_masked: form.kyc_pan_masked,
        bank_account_masked: form.bank_account_masked,
        kyc_gstin: form.kyc_gstin || null,
        kyc_reference: form.kyc_reference || null,
      });
      status.reload();
      toast("Payout details submitted for verification");
    } catch (reason) {
      setFormError(reason instanceof Error ? reason.message : "Payout details were not submitted");
    } finally { setBusy(false); }
  }

  if (status.loading) return <Panel className="panel-pad"><Skeleton rows={4}/></Panel>;
  if (status.error) return <Panel><ErrorState message={status.error} onRetry={status.reload}/></Panel>;
  if (!status.data) return null;

  const copy = payoutRoutingCopy(status.data);
  const verified = status.data.kyc.status === "verified";

  return <>
    <Panel className="panel-pad">
      <SectionHeading title="Payout routing" detail={copy.detail}
        action={<StatePill value={payoutRoutingPill(status.data)}/>}/>
      <div className="detail-grid">
        <div className="detail-field"><span>Commission</span><strong>{commissionRateLabel(status.data)}</strong></div>
        <div className="detail-field"><span>Razorpay account</span><strong>{maskAccountId(status.data.linked_account_id)}</strong></div>
        <div className="detail-field"><span>Routed to your account</span><strong>{formatRupees(status.data.routed_inr)}</strong></div>
        <div className="detail-field"><span>Planned · waiting on the provider</span><strong>{formatRupees(status.data.planned_inr)}</strong></div>
      </div>
      {status.data.failed_transfers ? <div className="warning-copy" style={{ marginTop: 14 }}>
        {status.data.failed_transfers} transfer(s) failed. Raise a support ticket with the transfer reference below so VoltStop can reconcile it.
      </div> : null}
    </Panel>

    <Panel className="panel-pad">
      <SectionHeading title={verified ? "Verified payout details" : "Payout details for verification"}
        detail="VoltStop only keeps the masked forms below. Your full PAN, IFSC and account number stay with Razorpay, which is the party that verifies them."/>
      {verified
        ? <div className="detail-grid">
            <div className="detail-field"><span>PAN</span><strong>{status.data.kyc.pan_masked ?? "—"}</strong></div>
            <div className="detail-field"><span>Bank account</span><strong>{status.data.kyc.bank_account_masked ?? "—"}</strong></div>
            <div className="detail-field"><span>GSTIN</span><strong>{status.data.kyc.gstin ?? "Not provided"}</strong></div>
            <div className="detail-field"><span>Verified</span><strong>{status.data.kyc.verified_at ?? "—"}</strong></div>
          </div>
        : <form onSubmit={submitKyc}>
            {formError && <p className="form-error" role="alert">{formError}</p>}
            <div className="form-grid">
              <label className="label-control">Masked PAN<input className="input-control" required maxLength={10}
                value={form.kyc_pan_masked} placeholder="ABCDE****F"
                onChange={(event) => setForm({ ...form, kyc_pan_masked: event.target.value.toUpperCase() })}/></label>
              <label className="label-control">Masked bank account<input className="input-control" required maxLength={18}
                value={form.bank_account_masked} placeholder="*****1234"
                onChange={(event) => setForm({ ...form, bank_account_masked: event.target.value })}/></label>
              <label className="label-control">GSTIN (optional)<input className="input-control" maxLength={15}
                value={form.kyc_gstin} placeholder="29ABCDE1234F1Z5"
                onChange={(event) => setForm({ ...form, kyc_gstin: event.target.value.toUpperCase() })}/></label>
              <label className="label-control">Provider reference (optional)<input className="input-control" maxLength={120}
                value={form.kyc_reference} placeholder="Razorpay KYC or trade licence reference"
                onChange={(event) => setForm({ ...form, kyc_reference: event.target.value })}/></label>
            </div>
            <div className="form-actions"><span className="label-note">Submitting sends your details to VoltStop for review; routing starts only after an operator verifies them.</span>
              <Button disabled={busy || !token}>{busy ? "Submitting…" : status.data.kyc.status === "not_started" ? "Submit payout details" : "Update payout details"}</Button></div>
          </form>}
    </Panel>

    <Panel className="panel-pad">
      <SectionHeading title="Settlement transfers" detail="One row per captured booking that was split toward your account. Planned rows are instructions sent with the payment; only provider-confirmed rows count as money routed."/>
      {transfers.loading ? <Skeleton rows={4}/> : transfers.error ? <ErrorState message={transfers.error} onRetry={transfers.reload}/>
        : !transfers.data?.items.length ? <EmptyState title="No transfers yet" description="Transfers appear once routing is live and a booking payment is captured."/>
        : <div className="data-table-wrap"><table className="data-table">
          <thead><tr><th>Source</th><th>Booked amount</th><th>Your share</th><th>Commission</th><th>Rate</th><th>Status</th><th>Reference</th></tr></thead>
          <tbody>{transfers.data.items.map((row) => <tr key={row.id}>
            <td className="table-primary">{row.source_kind.replaceAll("_", " ")}</td>
            <td>{formatRupees(row.gross_amount_inr)}</td>
            <td>{formatRupees(row.vendor_amount_inr)}</td>
            <td>{formatRupees(row.commission_inr)}</td>
            <td>{row.rate_bps / 100}%</td>
            <td><StatePill value={transferStatusLabel(row)}/></td>
            <td><small className="table-note">{row.razorpay_transfer_id ?? row.settlement_utr ?? row.razorpay_order_id ?? "—"}</small></td>
          </tr>)}</tbody>
        </table></div>}
      <div className="table-footnote"><span><Icon name="credit" size={13}/> Amounts are in INR and come from the payout ledger, not from an estimate.</span></div>
    </Panel>
  </>;
}
