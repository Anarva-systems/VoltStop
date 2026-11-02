import { assertEquals, assertStringIncludes } from "jsr:@std/assert";
import { Webhook } from "https://esm.sh/standardwebhooks@1.0.0";
import { handleSmsHook } from "./index.ts";

const SECRET = "v1,whsec_" + btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(32))));

function signedRequest(payload: unknown): Request {
  const body = JSON.stringify(payload);
  const id = crypto.randomUUID();
  const timestamp = new Date();
  return new Request("http://localhost/send-sms", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "webhook-id": id,
      "webhook-timestamp": String(Math.floor(timestamp.getTime() / 1000)),
      "webhook-signature": new Webhook(SECRET.replace(/^v1,whsec_/, "")).sign(id, timestamp, body),
    },
    body,
  });
}

function configuredEnv(): Record<string, string> {
  return {
    SEND_SMS_HOOK_SECRET: SECRET,
    MSG91_AUTHKEY: "authkey-test",
    MSG91_OTP_TEMPLATE_ID: "template-test",
  };
}

async function withEnvironment<T>(
  overrides: Partial<Record<keyof ReturnType<typeof configuredEnv>, string | undefined>>,
  run: () => Promise<T>,
): Promise<T> {
  const settings = { ...configuredEnv(), ...overrides };
  for (const [name, value] of Object.entries(settings)) {
    if (value === undefined) Deno.env.delete(name);
    else Deno.env.set(name, value);
  }
  try {
    return await run();
  } finally {
    for (const name of Object.keys(settings)) Deno.env.delete(name);
  }
}

async function withStubbedFetch<T>(
  responder: (request: Request) => Response | Promise<Response>,
  run: (calls: Request[]) => Promise<T>,
): Promise<T> {
  const calls: Request[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(String(input), init);
    calls.push(request.clone());
    const response = await responder(request);
    return new Response(response.body, { status: response.status, headers: response.headers });
  }) as typeof fetch;
  try {
    return await run(calls);
  } finally {
    globalThis.fetch = original;
  }
}

Deno.test("rejects a request the hook secret did not sign", async () => {
  await withEnvironment({}, async () => {
    const response = await handleSmsHook(
      new Request("http://localhost/send-sms", {
        method: "POST",
        body: JSON.stringify({ user: { phone: "+919876543210" }, sms: { otp: "123456" } }),
      }),
    );
    assertEquals(response.status, 401);
  });
});

Deno.test("hands the Supabase OTP to MSG91 as digits-only mobile", async () => {
  await withEnvironment({}, async () => {
    await withStubbedFetch(
      () => new Response(JSON.stringify({ type: "success", message: "request-id-1" }), { status: 200 }),
      async (calls) => {
        const response = await handleSmsHook(signedRequest({ user: { phone: "+919876543210" }, sms: { otp: "123456" } }));
        assertEquals(response.status, 200);
        assertEquals(await response.text(), "{}");

        const url = new URL(calls[0].url);
        assertEquals(url.pathname, "/api/v5/otp");
        assertEquals(url.searchParams.get("mobile"), "919876543210");
        assertEquals(url.searchParams.get("otp"), "123456");
        assertEquals(url.searchParams.get("template_id"), "template-test");
        assertEquals(calls[0].headers.get("authkey"), "authkey-test");
      },
    );
  });
});

Deno.test("treats an MSG91 error envelope as a failure, without leaking it to the app", async () => {
  await withEnvironment({}, async () => {
    await withStubbedFetch(
      () => new Response(JSON.stringify({ type: "error", message: "Template ID invalid for authkey-test" }), { status: 200 }),
      async () => {
        const response = await handleSmsHook(signedRequest({ user: { phone: "+919876543210" }, sms: { otp: "123456" } }));
        assertEquals(response.status, 502);
        const body = await response.text();
        assertStringIncludes(body, "SMS provider could not send the code.");
        assertEquals(body.includes("authkey-test"), false);
        assertEquals(body.includes("123456"), false);
      },
    );
  });
});

Deno.test("reports a provider network failure instead of a false success", async () => {
  await withEnvironment({}, async () => {
    await withStubbedFetch(
      () => {
        throw new Error("connect: connection refused");
      },
      async () => {
        const response = await handleSmsHook(signedRequest({ user: { phone: "+919876543210" }, sms: { otp: "123456" } }));
        assertEquals(response.status, 502);
      },
    );
  });
});

Deno.test("does not call MSG91 when its credentials are missing", async () => {
  await withEnvironment({ MSG91_AUTHKEY: undefined }, async () => {
    await withStubbedFetch(
      () => new Response(JSON.stringify({ type: "success" }), { status: 200 }),
      async (calls) => {
        const response = await handleSmsHook(signedRequest({ user: { phone: "+919876543210" }, sms: { otp: "123456" } }));
        assertEquals(response.status, 502);
        assertEquals(calls.length, 0);
      },
    );
  });
});

Deno.test("rejects a signed payload with no OTP", async () => {
  await withEnvironment({}, async () => {
    await withStubbedFetch(
      () => new Response(JSON.stringify({ type: "success" }), { status: 200 }),
      async (calls) => {
        const response = await handleSmsHook(signedRequest({ user: { phone: "+919876543210" } }));
        assertEquals(response.status, 400);
        assertEquals(calls.length, 0);
      },
    );
  });
});
