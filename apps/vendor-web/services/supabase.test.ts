import assert from "node:assert/strict";
import { test } from "node:test";
import { initializeSupabaseBrowserClient, resolveSupabaseBrowserConfig, supabaseBrowserConfigurationError } from "./supabase.ts";
import { mapSupabasePublicEnvironment } from "./supabase-build-config.ts";

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


test("missing browser configuration returns a clear diagnostic", () => {
  assert.match(
    supabaseBrowserConfigurationError({}) ?? "",
    /NEXT_PUBLIC_SUPABASE_URL|SUPABASE_URL/,
  );
  assert.match(
    supabaseBrowserConfigurationError({ NEXT_PUBLIC_SUPABASE_URL: projectUrl }) ?? "",
    /public key/,
  );
  assert.equal(resolveSupabaseBrowserConfig({}), null);
});

test("production Supabase URLs reject localhost and insecure HTTP", () => {
  assert.match(
    supabaseBrowserConfigurationError({
      NEXT_PUBLIC_SUPABASE_URL: "http://127.0.0.1:54321",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "legacy_anon_test_fixture",
      NODE_ENV: "production",
    }) ?? "",
    /HTTPS URL/,
  );
});

test("Vercel integration values map to public browser names", () => {
  assert.deepEqual(
    mapSupabasePublicEnvironment({
      SUPABASE_URL: projectUrl,
      SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test_fixture",
    }),
    {
      NEXT_PUBLIC_SUPABASE_URL: projectUrl,
      NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test_fixture",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "",
    },
  );
});

test("server credentials other than anon or publishable keys are never mapped", () => {
  const mapped = mapSupabasePublicEnvironment({
    SUPABASE_URL: projectUrl,
    SUPABASE_SERVICE_ROLE_KEY: "must_not_be_exposed",
    SUPABASE_SECRET_KEY: "must_not_be_exposed",
  });
  assert.equal(mapped.NEXT_PUBLIC_SUPABASE_URL, projectUrl);
  assert.equal(mapped.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY, "");
  assert.equal(mapped.NEXT_PUBLIC_SUPABASE_ANON_KEY, "");
  assert.equal("NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY" in mapped, false);
});


test("configured project URL and public key initialize a Supabase client", () => {
  const client = initializeSupabaseBrowserClient({
    NEXT_PUBLIC_SUPABASE_URL: projectUrl,
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test_fixture",
  });
  assert.ok(client);
  assert.equal(typeof client.auth.signInWithPassword, "function");
});
