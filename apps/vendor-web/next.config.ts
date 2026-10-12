import type { NextConfig } from "next";
import { mapSupabasePublicEnvironment } from "./services/supabase-build-config";

const nextConfig: NextConfig = {
  // Next.js embeds these explicitly approved public values and safe source labels into the browser bundle.
  // This also bridges Vercel's Supabase integration variable names at build time.
  env: mapSupabasePublicEnvironment(process.env),
};

export default nextConfig;
