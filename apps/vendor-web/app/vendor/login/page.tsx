"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/portal";
import { useVendorAuth } from "@/components/vendor-auth";
import { resolveRole } from "@/services/resolve-role";
import { formatSupabaseAuthError, isSupabaseEmailConfirmationError, supabaseBrowserClient, supabaseBrowserConfigurationError } from "@/services/supabase";

export default function VendorLoginPage() {
  const router = useRouter();
  const { user, session, loading } = useVendorAuth();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirmationEmail, setConfirmationEmail] = useState("");
  const [resendBusy, setResendBusy] = useState(false);
  const configurationError = supabaseBrowserConfigurationError();
  const configured = configurationError === null;

  useEffect(() => {
    if (loading || !user || !session?.access_token) return;
    let active = true;
    void resolveRole(session.access_token, { allowVendorSetup: true })
      .then((destination) => { if (active) router.replace(destination); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "We couldn’t verify your VoltStop role."); });
    return () => { active = false; };
  }, [loading, router, session?.access_token, user]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    setConfirmationEmail("");
    const client = supabaseBrowserClient();
    if (!client) { setError("Supabase sign-in is not configured for this deployment."); return; }
    setBusy(true);
    try {
      if (mode === "login") {
        const { data, error: authError } = await client.auth.signInWithPassword({ email: email.trim(), password });
        if (authError) throw authError;
        if (!data.session) throw new Error("The authenticated session was not returned. Please try again.");
        router.replace(await resolveRole(data.session.access_token, { allowVendorSetup: true }));
        router.refresh();
      } else {
        const { data, error: authError } = await client.auth.signUp({
          email: email.trim(),
          password,
          options: { emailRedirectTo: `${window.location.origin}/vendor/login` },
        });
        if (authError) throw authError;
        if (data.session) {
          router.replace(await resolveRole(data.session.access_token, { allowVendorSetup: true }));
          router.refresh();
        } else {
          setConfirmationEmail(email.trim());
          setNotice("Your account was created and needs email confirmation. Supabase accepted the request, but that does not guarantee the email was delivered. Check spam, or resend below.");
        }
      }
    } catch (reason) {
      if (mode === "login" && isSupabaseEmailConfirmationError(reason)) {
        setConfirmationEmail(email.trim());
        setError("This account’s email is not confirmed yet, so sign-in is blocked. Resend the confirmation link below.");
      } else if (reason instanceof Error && (
        (mode === "login" && /invalid login credentials/i.test(reason.message)) ||
        (mode === "signup" && /user already registered|already been registered/i.test(reason.message))
      )) {
        setConfirmationEmail(email.trim());
        setError("Check your email and password. If this account was just registered, it may still need email confirmation; request a new link below.");
      } else {
        setError(formatSupabaseAuthError(reason));
      }
    } finally { setBusy(false); }
  }

  async function resendConfirmation() {
    const client = supabaseBrowserClient();
    if (!client || !confirmationEmail) return;
    setError("");
    setNotice("");
    setResendBusy(true);
    try {
      const { error: resendError } = await client.auth.resend({
        type: "signup",
        email: confirmationEmail,
        options: { emailRedirectTo: `${window.location.origin}/vendor/login` },
      });
      if (resendError) throw resendError;
      setNotice("Supabase accepted the resend request. Check spam; if no email arrives, the project owner needs to configure custom SMTP and review Supabase Auth email logs.");
    } catch (reason) {
      setError(formatSupabaseAuthError(reason));
    } finally {
      setResendBusy(false);
    }
  }

  return <main className="auth-page">
    <section className="auth-art">
      <Link href="/" className="auth-brand"><span className="brand-symbol">V</span><span>VOLT<span className="brand-green">STOP</span></span></Link>
      <div className="auth-art-copy"><p className="eyebrow">HIGHWAY PARTNER OPERATIONS</p><h1>Keep every stop running.</h1><p>Manage bookings, charging capacity and services from one clear workspace built for the NH-16 corridor.</p><div className="auth-corridor"><i/>Srikakulam <Icon name="arrow" size={15}/> Vijayawada<span className="topbar-live"><i/> Live pilot</span></div></div>
      <div className="auth-art-footer">VoltStop partner network · Andhra Pradesh</div>
    </section>
    <section className="auth-side">
      <div className="auth-card">
        <p className="eyebrow">PARTNER PORTAL</p><h2>{mode === "login" ? "Welcome back" : "Create your account"}</h2>
        <p>{mode === "login" ? "Sign in with the Supabase account linked to your business." : "Create a Supabase account to start a vendor profile."}</p>
        <form className="auth-form" onSubmit={submit}>
          <label className="label-control">Business email<input required type="email" autoComplete="email" className="input-control" placeholder="you@yourbusiness.in" value={email} onChange={(event) => setEmail(event.target.value)}/></label>
          <label className="label-control">Password<span className="auth-password-field"><input required minLength={6} type={showPassword ? "text" : "password"} autoComplete={mode === "login" ? "current-password" : "new-password"} className="input-control" placeholder="At least 6 characters" value={password} onChange={(event) => setPassword(event.target.value)}/><button type="button" aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword((visible) => !visible)}>{showPassword ? "Hide" : "Show"}</button></span></label>
          <button className="button button-primary auth-submit" disabled={busy || !configured}>{busy ? <><span className="spinner"/>Working…</> : <>{mode === "login" ? "Sign in" : "Create account"}<Icon name="arrow"/></>}</button>
        </form>
        {error && <p role="alert" className="auth-message">{error}</p>}
        {notice && <p role="status" className="auth-message auth-success-message">{notice}</p>}
        {confirmationEmail && <div className="auth-confirmation">
          <button type="button" className="auth-switch auth-link-button" disabled={resendBusy || busy || !configured} onClick={() => void resendConfirmation()}>
            {resendBusy ? "Sending confirmation…" : `Resend confirmation to ${confirmationEmail}`}
          </button>
          <p className="auth-hint">Supabase’s built-in email sender is restricted and rate-limited. For reliable delivery, configure a custom SMTP provider in the project’s Auth settings.</p>
        </div>}
        <div className="auth-switch">{mode === "login" ? "New to VoltStop? " : "Already registered? "}<button onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(""); setNotice(""); setConfirmationEmail(""); }}>{mode === "login" ? "Create an account" : "Sign in"}</button></div>
        {!configured && <div role="status" className="auth-config-warning">Supabase sign-in is unavailable. {configurationError ?? "Check the deployment configuration."}</div>}
        <p className="auth-switch"><Link href="/">← VoltStop home</Link></p>
      </div>
    </section>
  </main>;
}
