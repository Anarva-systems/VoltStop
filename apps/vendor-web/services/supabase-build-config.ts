/**
 * Build-time aliases for Supabase values that are safe to publish in browser code.
 * Never add the service-role key or any secret credential here.
 */
export type SupabaseBuildEnvironment = Record<string, string | undefined>;

export function mapSupabasePublicEnvironment(
  source: SupabaseBuildEnvironment,
): Record<string, string> {
  const urlSource = source.NEXT_PUBLIC_SUPABASE_URL?.trim()
    ? "NEXT_PUBLIC_SUPABASE_URL"
    : source.SUPABASE_URL?.trim()
      ? "SUPABASE_URL"
      : "missing";
  const keySource = source.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim()
    ? "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"
    : source.SUPABASE_PUBLISHABLE_KEY?.trim()
      ? "SUPABASE_PUBLISHABLE_KEY"
      : source.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim()
        ? "NEXT_PUBLIC_SUPABASE_ANON_KEY"
        : source.SUPABASE_ANON_KEY?.trim()
          ? "SUPABASE_ANON_KEY"
          : "missing";
  return {
    NEXT_PUBLIC_SUPABASE_URL:
      source.NEXT_PUBLIC_SUPABASE_URL?.trim() || source.SUPABASE_URL?.trim() || "",
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY:
      source.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim() ||
      source.SUPABASE_PUBLISHABLE_KEY?.trim() ||
      "",
    NEXT_PUBLIC_SUPABASE_ANON_KEY:
      source.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim() || source.SUPABASE_ANON_KEY?.trim() || "",
    // These labels are safe build metadata and let login errors identify the
    // selected setting without exposing any credential value.
    NEXT_PUBLIC_VOLTSTOP_SUPABASE_URL_SOURCE: urlSource,
    NEXT_PUBLIC_VOLTSTOP_SUPABASE_KEY_SOURCE: keySource,
  };
}
