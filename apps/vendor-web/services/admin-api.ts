import type { ApiFailure, ApiSuccess } from "@/types/api";
import { getApiBaseUrl } from "@/services/api-config";

export async function adminApi<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const apiBaseUrl = getApiBaseUrl();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/admin${path}`, { ...init, headers, cache: "no-store" });
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

export function adminGet<T>(path: string, token: string) { return adminApi<T>(path, token); }

export function adminPost<T>(path: string, token: string, value?: unknown, headers?: Record<string, string>) {
  return adminApi<T>(path, token, { method: "POST", headers, ...(value === undefined ? {} : { body: JSON.stringify(value) }) });
}

export function adminPatch<T>(path: string, token: string, value: unknown) {
  return adminApi<T>(path, token, { method: "PATCH", body: JSON.stringify(value) });
}
