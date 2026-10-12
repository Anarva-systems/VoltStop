import assert from "node:assert/strict";
import { test } from "node:test";
import { resolveSupabaseBrowserConfig } from "./supabase.ts";

const projectUrl = "https://voltstop-test.supabase.co";

test("uses the Vercel integration's browser publishable key", () => {
  assert.deepEqual(
    resolveSupabaseBrowserConfig({
      NEXT_PUBLIC_SUPABASE_URL: projectUrl,
      NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test_fixture",
    }),
    { url: projectUrl, key: "sb_publishable_test_fixture" },
  );
});

test("keeps support for the existing public anon-key setting", () => {
  assert.deepEqual(
    resolveSupabaseBrowserConfig({
      NEXT_PUBLIC_SUPABASE_URL: projectUrl,
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "legacy_anon_test_fixture",
    }),
    { url: projectUrl, key: "legacy_anon_test_fixture" },
  );
});

test("prefers publishable key when both public key names are configured", () => {
  assert.equal(
    resolveSupabaseBrowserConfig({
      NEXT_PUBLIC_SUPABASE_URL: projectUrl,
      NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test_fixture",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "legacy_anon_test_fixture",
    })?.key,
    "sb_publishable_test_fixture",
  );
});

test("does not expose server-only integration variables to browser configuration", () => {
  assert.equal(
    resolveSupabaseBrowserConfig({
      SUPABASE_URL: projectUrl,
      SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test_fixture",
    }),
    null,
  );
});
