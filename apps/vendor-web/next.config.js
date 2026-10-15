const path = require("node:path");

function mapSupabasePublicEnvironment(source) {
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
    NEXT_PUBLIC_VOLTSTOP_SUPABASE_URL_SOURCE: urlSource,
    NEXT_PUBLIC_VOLTSTOP_SUPABASE_KEY_SOURCE: keySource,
  };
}

module.exports = {
  // Explicit monorepo root keeps deployment output tracing stable.
  outputFileTracingRoot: path.join(__dirname, "../.."),
  // Only the public Supabase URL and publishable/anon key are exposed to the browser.
  env: mapSupabasePublicEnvironment(process.env),
};
