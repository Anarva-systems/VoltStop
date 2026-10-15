import { adminGet } from "@/services/admin-api";
import { apiGet } from "@/services/api";

type ResolveRoleOptions = {
  /** Allow an authenticated partner with no profile to enter vendor onboarding. */
  allowVendorSetup?: boolean;
};

/** Resolve the authenticated destination from server-authoritative role APIs. */
export async function resolveRole(token: string, options: ResolveRoleOptions = {}): Promise<string> {
  try {
    await adminGet("/me", token);
    return "/admin";
  } catch (reason) {
    const adminStatus = getStatus(reason);
    if (adminStatus === undefined && reason instanceof Error) throw reason;
    if (adminStatus !== 403) {
      throw new Error(adminStatus === 401
        ? "Your session could not be verified. Please sign in again."
        : "Your VoltStop role could not be verified. Check the API status and try again.");
    }
  }

  try {
    await apiGet("/profile", token);
    return "/vendor/dashboard";
  } catch (reason) {
    const vendorStatus = getStatus(reason);
    if (vendorStatus === undefined && reason instanceof Error) throw reason;
    if (vendorStatus === 404 && options.allowVendorSetup) return "/vendor/profile";
    if (vendorStatus === 404) {
      throw new Error("You’re signed in, but this account has no VoltStop role yet. Ask a VoltStop administrator to assign admin access, or use Partner sign-in to create a vendor profile.");
    }
    if (vendorStatus === 401) throw new Error("Your session could not be verified. Please sign in again.");
    throw new Error("Your vendor profile could not be verified. Check the API status and try again.");
  }
}

function getStatus(reason: unknown): number | undefined {
  return reason instanceof Error ? (reason as Error & { status?: number }).status : undefined;
}
