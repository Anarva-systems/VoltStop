import type { PayoutStatus, PayoutTransfer } from "@/types/vendor";

const ROUTING_COPY: Record<string, { label: string; detail: string }> = {
  routing_enabled: {
    label: "Payout routing is live",
    detail: "Captured bookings are split to your Razorpay account and each transfer is ledgered below.",
  },
  ready_disabled: {
    label: "Ready · platform routing is switched off",
    detail: "Your account is verified and linked, but VoltStop has not switched on automatic transfers yet.",
  },
  disabled: {
    label: "Payouts paused",
    detail: "VoltStop has paused transfers to this account. Contact support to resume them.",
  },
  kyc_required: {
    label: "Waiting on KYC verification",
    detail: "Submit your payout details below; VoltStop reviews them before transfers start.",
  },
  account_required: {
    label: "Razorpay account not linked",
    detail: "VoltStop still has to connect your Razorpay account. Until then payments stay with the platform.",
  },
  approval_required: {
    label: "Waiting on business approval",
    detail: "Your vendor profile must be approved before payouts can be routed.",
  },
  rate_invalid: {
    label: "Commission setting needs a correction",
    detail: "The recorded commission rate leaves the platform too little to settle, so transfers stay paused.",
  },
  blocked: { label: "Estimates only", detail: "Payout routing is not available for this account yet." },
};

export function payoutRoutingCopy(status: Pick<PayoutStatus, "state"> | null): { label: string; detail: string } {
  if (!status) return ROUTING_COPY.blocked;
  return ROUTING_COPY[status.state] ?? ROUTING_COPY.blocked;
}

const PILL_BY_STATE: Record<string, string> = {
  routing_enabled: "captured",
  ready_disabled: "limited",
  disabled: "closed",
  kyc_required: "pending",
  account_required: "pending",
  approval_required: "authorized",
  rate_invalid: "failed",
};

export function payoutRoutingPill(status: Pick<PayoutStatus, "state"> | null): string {
  return PILL_BY_STATE[status?.state ?? ""] ?? "estimate_only";
}

export function commissionRateLabel(status: Pick<PayoutStatus, "commission_rate_bps" | "commission_rate_source"> | null): string {
  if (!status || status.commission_rate_bps === null || status.commission_rate_bps === undefined) return "Commission rate not recorded";
  const percent = status.commission_rate_bps / 100;
  const source = status.commission_rate_source === "vendor_override" ? "agreed rate for your business" : "standard platform rate";
  return `${percent.toLocaleString("en-IN", { maximumFractionDigits: 2 })}% commission · ${source}`;
}

export function maskAccountId(value: string | null | undefined): string {
  const id = value ?? "";
  if (!id.startsWith("acc_")) return id || "Not linked yet";
  if (id.length <= 10) return `${id.slice(0, 4)}••••`;
  return `${id.slice(0, 6)}${"•".repeat(id.length - 10)}${id.slice(-4)}`;
}

const PAN_MASK = /^[A-Z]{5}\*{4}[A-Z0-9]$/;
const BANK_MASK = /^\*{4,13}[0-9]{4}$/;
const GSTIN = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$/;

export function kycValidationError(values: { kyc_pan_masked: string; bank_account_masked: string; kyc_gstin?: string }): string | null {
  if (!PAN_MASK.test(values.kyc_pan_masked)) {
    return "Enter the PAN as it appears on your Razorpay account, with the last four digits hidden, for example ABCDE****F.";
  }
  if (!BANK_MASK.test(values.bank_account_masked)) {
    return "Enter only the masked bank account, asterisks followed by the last four digits, for example *****1234.";
  }
  if (values.kyc_gstin && !GSTIN.test(values.kyc_gstin)) {
    return "A GSTIN is 15 characters, for example 29ABCDE1234F1Z5. Leave it blank if you do not have one.";
  }
  return null;
}

export function transferStatusLabel(row: Pick<PayoutTransfer, "status">): string {
  return row.status === "planned" ? "planned_not_sent" : row.status;
}

export const RAZORPAY_LINKED_ACCOUNT = /^acc_[A-Za-z0-9]{6,60}$/;

// Mirrors MINIMUM_PLATFORM_RETENTION_BPS in the API: a commission rate thinner than the
// provider fee plus its floor never produces a transfer, so the form refuses it up front
// instead of letting an operator save a routing config that silently routes nothing.
export const PLATFORM_RETENTION_FLOOR_BPS = 300;
export const MAX_COMMISSION_RATE_BPS = 5000;

export function payoutRoutingValidationError(values: {
  linked_account_id: string;
  commission_rate_bps: string;
  reason: string;
  payouts_enabled: boolean;
  account_on_file: boolean;
}): string | null {
  const account = values.linked_account_id.trim();
  if (account && !RAZORPAY_LINKED_ACCOUNT.test(account)) {
    return "A Razorpay linked account is acc_ followed by 6-60 letters or digits. Copy it from the provider dashboard.";
  }
  const rate = values.commission_rate_bps.trim();
  if (rate) {
    const parsed = Number(rate);
    if (!Number.isInteger(parsed) || parsed < PLATFORM_RETENTION_FLOOR_BPS || parsed > MAX_COMMISSION_RATE_BPS) {
      return `Commission must be a whole number between ${PLATFORM_RETENTION_FLOOR_BPS} and ${MAX_COMMISSION_RATE_BPS} bps. Below ${PLATFORM_RETENTION_FLOOR_BPS} VoltStop cannot cover the provider fee, so transfers would stop silently.`;
    }
  }
  if (values.reason.trim().length < 8) return "Record why this change is being made, in at least 8 characters.";
  if (values.payouts_enabled && !account && !values.account_on_file) {
    return "Routing needs a linked account on file before it can be switched on.";
  }
  return null;
}

// Ledger amounts are paise-exact, so the payout view keeps two decimals instead of
// rounding to whole rupees the way the general portal formatter does.
const rupees = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatRupees(value: string | number | null | undefined): string {
  const amount = Number(value ?? 0);
  return rupees.format(Number.isFinite(amount) ? amount : 0);
}
