import assert from "node:assert/strict";
import { test } from "node:test";
import { formatSupabaseAuthError, getSupabaseBrowserDiagnostics, initializeSupabaseBrowserClient, resolveSupabaseBrowserConfig, supabaseBrowserConfigurationError } from "./supabase.ts";
import { mapSupabasePublicEnvironment } from "./supabase-build-config.ts";

const projectUrl = "https://voltstop-test.supabase.co";
const legacyAnonKey = `eyJhbGciOiJIUzI1NiJ9.${Buffer.from(JSON.stringify({ role: "anon", iss: projectUrl + "/auth/v1" })).toString("base64url")}.signature`;

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
      NEXT_PUBLIC_SUPABASE_ANON_KEY: legacyAnonKey,
    }),
    { url: projectUrl, key: legacyAnonKey },
  );
});

test("prefers publishable key when both public key names are configured", () => {
  assert.equal(
    resolveSupabaseBrowserConfig({
      NEXT_PUBLIC_SUPABASE_URL: projectUrl,
      NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test_fixture",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: legacyAnonKey,
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
      NEXT_PUBLIC_SUPABASE_ANON_KEY: legacyAnonKey,
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
      NEXT_PUBLIC_VOLTSTOP_SUPABASE_URL_SOURCE: "SUPABASE_URL",
      NEXT_PUBLIC_VOLTSTOP_SUPABASE_KEY_SOURCE: "SUPABASE_PUBLISHABLE_KEY",
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

test("safe diagnostics report selected sources, hostname, presence, and public key format", () => {
  const diagnostics = getSupabaseBrowserDiagnostics({
    NEXT_PUBLIC_SUPABASE_URL: projectUrl,
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test_fixture",
    NEXT_PUBLIC_VOLTSTOP_SUPABASE_URL_SOURCE: "SUPABASE_URL",
    NEXT_PUBLIC_VOLTSTOP_SUPABASE_KEY_SOURCE: "SUPABASE_PUBLISHABLE_KEY",
  });
  assert.deepEqual(diagnostics, {
    urlPresent: true,
    keyPresent: true,
    projectHostname: "voltstop-test.supabase.co",
    urlSource: "SUPABASE_URL",
    keySource: "SUPABASE_PUBLISHABLE_KEY",
    keyFormat: "publishable",
    projectMatch: "not_verifiable_from_key",
  });
  assert.equal(JSON.stringify(diagnostics).includes("sb_publishable_test_fixture"), false);
});

test("legacy anon diagnostics check project issuer without exposing the key", () => {
  const matching = getSupabaseBrowserDiagnostics({
    NEXT_PUBLIC_SUPABASE_URL: projectUrl,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: legacyAnonKey,
  });
  assert.equal(matching.keyFormat, "legacy_anon");
  assert.equal(matching.projectMatch, "matched");

  const mismatching = getSupabaseBrowserDiagnostics({
    NEXT_PUBLIC_SUPABASE_URL: "https://another-project.supabase.co",
    NEXT_PUBLIC_SUPABASE_ANON_KEY: legacyAnonKey,
  });
  assert.equal(mismatching.projectMatch, "mismatched");
  assert.equal(JSON.stringify(matching).includes(legacyAnonKey), false);
});

test("invalid API key errors include safe configuration diagnostics only", () => {
  const diagnostic = formatSupabaseAuthError(new Error("Invalid API key"), {
    NEXT_PUBLIC_SUPABASE_URL: projectUrl,
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test_fixture",
  });
  assert.match(diagnostic, /voltstop-test\.supabase\.co/);
  assert.match(diagnostic, /NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY/);
  assert.match(diagnostic, /key format: publishable/);
  assert.equal(diagnostic.includes("sb_publishable_test_fixture"), false);
});

test("browser configuration rejects secret and unrecognized key formats", () => {
  assert.match(supabaseBrowserConfigurationError({
    NEXT_PUBLIC_SUPABASE_URL: projectUrl,
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_secret_do_not_use",
  }) ?? "", /server-only/);
  assert.match(supabaseBrowserConfigurationError({
    NEXT_PUBLIC_SUPABASE_URL: projectUrl,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: "not-a-supabase-key",
  }) ?? "", /not a recognized/);
});
