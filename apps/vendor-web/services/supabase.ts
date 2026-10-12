import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;

// Keep these as direct references: Next.js statically replaces NEXT_PUBLIC_*
// expressions during the build. Reading process.env as an object leaves them
// unavailable in the hydrated browser bundle.
const browserEnvironment = {
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY:
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  NEXT_PUBLIC_VOLTSTOP_SUPABASE_URL_SOURCE:
    process.env.NEXT_PUBLIC_VOLTSTOP_SUPABASE_URL_SOURCE,
  NEXT_PUBLIC_VOLTSTOP_SUPABASE_KEY_SOURCE:
    process.env.NEXT_PUBLIC_VOLTSTOP_SUPABASE_KEY_SOURCE,
  NODE_ENV: process.env.NODE_ENV,
};

export type SupabaseKeyFormat =
  | "publishable"
  | "legacy_anon"
  | "secret_or_service_role"
  | "unrecognized"
  | "missing";

export type SupabaseBrowserDiagnostics = {
  urlPresent: boolean;
  keyPresent: boolean;
  projectHostname: string | null;
  urlSource: string;
  keySource: string;
  keyFormat: SupabaseKeyFormat;
  projectMatch: "matched" | "mismatched" | "not_verifiable_from_key" | "unknown";
};

function classifySupabaseKey(key: string | undefined): SupabaseKeyFormat {
  if (!key) return "missing";
  if (key.startsWith("sb_secret_")) return "secret_or_service_role";
  if (key.startsWith("sb_publishable_") && /^sb_publishable_[A-Za-z0-9_-]+$/.test(key)) {
    return "publishable";
  }
  const parts = key.split(".");
  if (parts.length !== 3 || !parts[1]) return "unrecognized";
  try {
    const normalized = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=")));
    if (payload.role === "service_role" || payload.role === "supabase_admin") {
      return "secret_or_service_role";
    }
    return payload.role === "anon" ? "legacy_anon" : "unrecognized";
  } catch {
    return "unrecognized";
  }
}

function keyProjectMatch(key: string | undefined, hostname: string | null): SupabaseBrowserDiagnostics["projectMatch"] {
  if (!key || !hostname) return "unknown";
  if (key.startsWith("sb_publishable_")) return "not_verifiable_from_key";
  const parts = key.split(".");
  if (parts.length !== 3 || !parts[1]) return "unknown";
  try {
    const normalized = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=")));
    const issuerHost = typeof payload.iss === "string" ? new URL(payload.iss).hostname : null;
    const projectRef = typeof payload.ref === "string" ? payload.ref : null;
    const hostRef = hostname.endsWith(".supabase.co") ? hostname.slice(0, -".supabase.co".length) : null;
    if (issuerHost) return issuerHost.toLowerCase() === hostname.toLowerCase() ? "matched" : "mismatched";
    if (projectRef && hostRef) return projectRef.toLowerCase() === hostRef.toLowerCase() ? "matched" : "mismatched";
  } catch {
    return "unknown";
  }
  return "unknown";
}

/** Safe diagnostic metadata only: never returns the URL path, key, prefix, or fingerprint. */
export function getSupabaseBrowserDiagnostics(
  env: Record<string, string | undefined> = browserEnvironment,
): SupabaseBrowserDiagnostics {
  const url = env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim() || env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
  let projectHostname: string | null = null;
  try {
    projectHostname = url ? new URL(url).hostname : null;
  } catch {
    projectHostname = null;
  }
  return {
    urlPresent: Boolean(url),
    keyPresent: Boolean(key),
    projectHostname,
    urlSource: env.NEXT_PUBLIC_VOLTSTOP_SUPABASE_URL_SOURCE || (url ? "NEXT_PUBLIC_SUPABASE_URL" : "missing"),
    keySource: env.NEXT_PUBLIC_VOLTSTOP_SUPABASE_KEY_SOURCE || (env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim() ? "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY" : env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim() ? "NEXT_PUBLIC_SUPABASE_ANON_KEY" : "missing"),
    keyFormat: classifySupabaseKey(key),
    projectMatch: keyProjectMatch(key, projectHostname),
  };
}

/** Replaces Supabase's low-level invalid-key message with safe deployment diagnostics. */
export function formatSupabaseAuthError(
  reason: unknown,
  env: Record<string, string | undefined> = browserEnvironment,
): string {
  const message = reason instanceof Error ? reason.message : "";
  if (!/invalid api key/i.test(message)) {
    return message || "We couldn’t complete sign-in.";
  }
  const diagnostic = getSupabaseBrowserDiagnostics(env);
  return `Supabase rejected the configured public key. Project: ${diagnostic.projectHostname ?? "URL unavailable"}; URL source: ${diagnostic.urlSource}; key source: ${diagnostic.keySource}; key format: ${diagnostic.keyFormat}; project match: ${diagnostic.projectMatch}. Verify that the selected public key is active and belongs to this Supabase project.`;
}

export function supabaseBrowserConfigurationError(
  env: Record<string, string | undefined> = browserEnvironment,
): string | null {
  const url = env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key =
    env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim() ||
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
  if (!url) {
    return "Set NEXT_PUBLIC_SUPABASE_URL or the Vercel SUPABASE_URL integration variable.";
  }
  if (!key) {
    return "Set a public key: NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY, NEXT_PUBLIC_SUPABASE_ANON_KEY, or the Vercel SUPABASE_PUBLISHABLE_KEY integration variable.";
  }
  const keyFormat = classifySupabaseKey(key);
  if (keyFormat === "secret_or_service_role") {
    return "A server-only Supabase key is configured for browser sign-in. Use a publishable key or legacy anon key instead.";
  }
  if (keyFormat === "unrecognized") {
    return "The configured Supabase key is not a recognized publishable or legacy anon key.";
  }

  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return "The Supabase project URL is invalid. Use the URL for the intended Supabase project.";
  }
  if (
    !["https:", "http:"].includes(parsed.protocol) ||
    !parsed.hostname ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash
  ) {
    return "The Supabase project URL must be an HTTP or HTTPS project origin.";
  }
  if (env.NODE_ENV === "production") {
    const host = parsed.hostname.toLowerCase();
    const localHost =
      host === "localhost" ||
      host === "127.0.0.1" ||
      host === "::1" ||
      host.endsWith(".local") ||
      /^\d{1,3}(?:\.\d{1,3}){3}$/.test(host);
    if (parsed.protocol !== "https:" || localHost) {
      return "Production sign-in requires the HTTPS URL of the production Supabase project.";
    }
  }
  return null;
}

/** Resolve the public browser client config. Supports Supabase publishable keys and legacy anon keys. */
export function resolveSupabaseBrowserConfig(
  env: Record<string, string | undefined> = browserEnvironment,
): { url: string; key: string } | null {
  if (supabaseBrowserConfigurationError(env)) return null;
  const url = env.NEXT_PUBLIC_SUPABASE_URL!.trim();
  const key =
    env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim() ||
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY!.trim();
  return { url, key };
}

export function initializeSupabaseBrowserClient(
  env: Record<string, string | undefined> = browserEnvironment,
): SupabaseClient | null {
  const config = resolveSupabaseBrowserConfig(env);
  if (!config) return null;
  return createClient(config.url, config.key, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  });
}

export function supabaseBrowserClient(): SupabaseClient | null {
  client ??= initializeSupabaseBrowserClient();
  return client;
}

export function isSupabaseConfigured(): boolean {
  return supabaseBrowserConfigurationError() === null;
}
