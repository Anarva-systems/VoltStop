import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;

/** Resolve the browser-safe Supabase URL/key pair from supported Vercel names. */
export function resolveSupabaseBrowserConfig(
  env: Record<string, string | undefined> = process.env,
): { url: string; key: string } | null {
  const url = env.NEXT_PUBLIC_SUPABASE_URL;
  const key = env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return null;
  return { url, key };
}

export function supabaseBrowserClient(): SupabaseClient | null {
  const config = resolveSupabaseBrowserConfig();
  if (!config) return null;
  client ??= createClient(config.url, config.key, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  });
  return client;
}

export function isSupabaseConfigured(): boolean {
  return resolveSupabaseBrowserConfig() !== null;
}
