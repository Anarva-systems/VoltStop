/**
 * Build-time aliases for Supabase values that are safe to publish in browser code.
 * Never add the service-role key or any secret credential here.
 */
export type SupabaseBuildEnvironment = Record<string, string | undefined>;

export function mapSupabasePublicEnvironment(
  source: SupabaseBuildEnvironment,
): Record<string, string> {
  return {
    NEXT_PUBLIC_SUPABASE_URL:
      source.NEXT_PUBLIC_SUPABASE_URL || source.SUPABASE_URL || "",
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY:
      source.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
      source.SUPABASE_PUBLISHABLE_KEY ||
      "",
    NEXT_PUBLIC_SUPABASE_ANON_KEY:
      source.NEXT_PUBLIC_SUPABASE_ANON_KEY || source.SUPABASE_ANON_KEY || "",
  };
}
