import type { ApiFailure, ApiSuccess } from "@/types/api";
import { getApiBaseUrl } from "@/services/api-config";

function responseErrorMessage(
  response: Response,
  body: ApiSuccess<unknown> | ApiFailure | null,
  path: string,
): string {
  if (response.status === 422 && path.endsWith("/profile") && body && !body.success) {
    const fields = new Set(
      body.error.details?.flatMap((detail) =>
        detail.loc?.filter((part): part is string => typeof part === "string") ?? [],
      ) ?? [],
    );
    if (fields.has("lat") || fields.has("lng")) {
      return "Choose a point on the map and confirm it with Use this location.";
    }
    if (fields.has("name")) return "Enter a valid business name.";
    if (fields.has("address")) return "Enter a valid business address.";
    if (fields.has("type")) return "Choose a valid business type.";
    if (fields.has("image_url")) return "Use an image URL that starts with https:// or http://.";
    return "Check the business details and map location, then try again.";
  }
  return body && !body.success
    ? body.error.message
    : "The server returned an unexpected response.";
}

export async function vendorApi<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const apiBaseUrl = getApiBaseUrl();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/vendor${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new Error("VoltStop API is unreachable. Check the API URL and server status.");
  }
  const body = (await response.json().catch(() => null)) as ApiSuccess<T> | ApiFailure | null;
  if (!response.ok || !body || !body.success) {
    const message = responseErrorMessage(response, body, `/vendor${path}`);
    const error = new Error(message) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return body.data;
}

export async function userApi<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const apiBaseUrl = getApiBaseUrl();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response: Response;
  try { response = await fetch(`${apiBaseUrl}${path}`, { ...init, headers, cache: "no-store" }); }
  catch { throw new Error("VoltStop API is unreachable. Check the API URL and server status."); }
  const body = (await response.json().catch(() => null)) as ApiSuccess<T> | ApiFailure | null;
  if (!response.ok || !body || !body.success) {
    const message = responseErrorMessage(response, body, path);
    const error = new Error(message) as Error & { status?: number }; error.status = response.status; throw error;
  }
  return body.data;
}

export async function apiGet<T>(path: string, token: string): Promise<T> {
  return vendorApi<T>(path, token);
}

export async function apiPost<T>(path: string, token: string, value?: unknown): Promise<T> {
  return vendorApi<T>(path, token, { method: "POST", ...(value === undefined ? {} : { body: JSON.stringify(value) }) });
}

export async function apiPatch<T>(path: string, token: string, value: unknown): Promise<T> {
  return vendorApi<T>(path, token, { method: "PATCH", body: JSON.stringify(value) });
}
