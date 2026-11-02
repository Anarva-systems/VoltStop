// Supabase Auth "Send phone message" hook: OTP delivery through MSG91's
// DLT-registered transactional route instead of Supabase's built-in provider.
// Activation (dashboard hook URI, secrets, DLT prerequisites) is in
// docs/sms-hook-msg91-2026-10-31.md.

import { Webhook } from "https://esm.sh/standardwebhooks@1.0.0";

const HOOK_SECRET = "SEND_SMS_HOOK_SECRET";
const MSG91_AUTHKEY = "MSG91_AUTHKEY";
const MSG91_OTP_TEMPLATE_ID = "MSG91_OTP_TEMPLATE_ID";
const MSG91_OTP_ENDPOINT = "https://control.msg91.com/api/v5/otp";
const PROVIDER_TIMEOUT_MS = 8_000;

type HookPayload = {
  user?: { phone?: string | null };
  sms?: { otp?: string | null };
};

type Msg91Response = {
  type?: string;
  message?: string;
};

function providerError(status: number, logDetail: string): Response {
  console.error(`[send-sms] ${logDetail}`);
  return json({ error: { http_code: status, message: "SMS provider could not send the code." } }, status);
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function signatureIsValid(request: Request, rawBody: string): boolean {
  const secret = Deno.env.get(HOOK_SECRET);
  if (!secret) return false;
  try {
    new Webhook(secret.replace(/^v1,whsec_/, "")).verify(rawBody, Object.fromEntries(request.headers));
    return true;
  } catch {
    return false;
  }
}

// MSG91 wants the digits of the E.164 number without the leading "+".
function digits(value: string | null | undefined): string {
  return (value ?? "").replace(/\D/g, "");
}

async function sendThroughMsg91(mobile: string, otp: string): Promise<string> {
  const authkey = Deno.env.get(MSG91_AUTHKEY);
  const templateId = Deno.env.get(MSG91_OTP_TEMPLATE_ID);
  if (!authkey || !templateId) {
    throw new Error("MSG91_AUTHKEY and MSG91_OTP_TEMPLATE_ID must both be set");
  }

  const url = new URL(MSG91_OTP_ENDPOINT);
  url.searchParams.set("template_id", templateId);
  url.searchParams.set("mobile", mobile);
  url.searchParams.set("otp", otp);

  const response = await fetch(url, {
    method: "POST",
    headers: { authkey, accept: "application/json" },
    signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
  });

  // MSG91 answers 200 for some rejections, so the envelope decides, not the status.
  let body: Msg91Response;
  try {
    body = (await response.json()) as Msg91Response;
  } catch {
    throw new Error(`MSG91 responded with status ${response.status} and a non-JSON body`);
  }
  if (!response.ok || body.type !== "success") {
    throw new Error(`MSG91 rejected the message (status ${response.status}): ${body.message ?? "no reason given"}`);
  }
  return body.message ?? "unknown";
}

export async function handleSmsHook(request: Request): Promise<Response> {
  const rawBody = await request.text();
  if (!signatureIsValid(request, rawBody)) {
    return json({ error: { http_code: 401, message: "Invalid hook signature." } }, 401);
  }

  const { user, sms } = JSON.parse(rawBody) as HookPayload;
  const otp = digits(sms?.otp);
  const mobile = digits(user?.phone);
  if (otp.length < 4 || mobile.length < 10) {
    return providerError(400, "Hook payload carried no usable OTP or phone number.");
  }

  try {
    const requestId = await sendThroughMsg91(mobile, otp);
    // The OTP and the full number stay out of the logs; MSG91 keys its own
    // delivery report on request_id.
    console.info(`[send-sms] provider accepted the request, request_id=${requestId}`);
    return json({});
  } catch (error) {
    return providerError(502, String(error instanceof Error ? error.message : error));
  }
}

if (import.meta.main) {
  Deno.serve(handleSmsHook);
}
