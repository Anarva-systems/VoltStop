import { adminGet } from "@/services/admin-api";
import { apiGet } from "@/services/api";

/** Resolve the authenticated destination from server-authoritative role APIs. */
export async function resolveRole(token: string): Promise<string> {
  try {
    await adminGet("/me", token);
    return "/admin";
  } catch (reason) {
    const adminStatus = getStatus(reason);
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
    if (vendorStatus === 404) return "/vendor/profile";
    if (vendorStatus === 401) throw new Error("Your session could not be verified. Please sign in again.");
    throw new Error("Your vendor profile could not be verified. Check the API status and try again.");
  }
}

function getStatus(reason: unknown): number | undefined {
  return reason instanceof Error ? (reason as Error & { status?: number }).status : undefined;
}
