import type { ApiFailure, ApiSuccess } from "@/types/api";
import { getApiBaseUrl } from "@/services/api-config";

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
    const message = body && !body.success ? body.error.message : "The server returned an unexpected response.";
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
    const message = body && !body.success ? body.error.message : "The server returned an unexpected response.";
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
