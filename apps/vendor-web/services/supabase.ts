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
  NODE_ENV: process.env.NODE_ENV,
};

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
