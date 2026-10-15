"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { resolveRole } from "@/services/resolve-role";
import { Icon } from "@/components/portal";
import { useVendorAuth } from "@/components/vendor-auth";
import { formatSupabaseAuthError, isSupabaseEmailConfirmationError, supabaseBrowserClient, supabaseBrowserConfigurationError } from "@/services/supabase";

export default function LoginPage() {
  const router = useRouter();
  const { user, session, loading } = useVendorAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [resetBusy, setResetBusy] = useState(false);
  const [resetMessage, setResetMessage] = useState("");
  const [confirmationEmail, setConfirmationEmail] = useState("");
  const [confirmationBusy, setConfirmationBusy] = useState(false);
  const [confirmationMessage, setConfirmationMessage] = useState("");
  const [error, setError] = useState("");
  const configurationError = supabaseBrowserConfigurationError();
  const configured = configurationError === null;

  useEffect(() => {
    if (!loading && user && session?.access_token) {
      resolveRole(session.access_token)
        .then((destination) => router.replace(destination))
        .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Your VoltStop role could not be verified."));
    }
  }, [loading, router, session?.access_token, user]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setConfirmationEmail("");
    setConfirmationMessage("");
    const client = supabaseBrowserClient();
    if (!client) {
      setError("Supabase sign-in is not configured for this deployment.");
      return;
    }
    setBusy(true);
    try {
      const { data, error: authError } = await client.auth.signInWithPassword({ email: email.trim(), password });
      if (authError) throw authError;
      if (!data.session) throw new Error("The authenticated session was not returned. Please try again.");
      router.replace(await resolveRole(data.session.access_token));
      router.refresh();
    } catch (reason) {
      if (isSupabaseEmailConfirmationError(reason)) {
        setConfirmationEmail(email.trim());
        setError("This account’s email is not confirmed yet, so sign-in is blocked. Resend the confirmation link below.");
      } else if (reason instanceof Error && /invalid login credentials/i.test(reason.message)) {
        setConfirmationEmail(email.trim());
        setError("Sign-in failed. Check your email and password. If you just registered, the account may still need email confirmation; you can request a new link below.");
      } else {
        setError(formatSupabaseAuthError(reason));
      }
    } finally {
      setBusy(false);
    }
  }

  async function sendPasswordReset() {
    setError("");
    setResetMessage("");
    const address = email.trim();
    if (!address) {
      setError("Enter your email address first, then choose Forgot password.");
      return;
    }
    const client = supabaseBrowserClient();
    if (!client) {
      setError("Supabase sign-in is not configured for this deployment.");
      return;
    }
    setResetBusy(true);
    try {
      const { error: resetError } = await client.auth.resetPasswordForEmail(address, {
        redirectTo: `${window.location.origin}/login/reset`,
      });
      if (resetError) throw resetError;
      setResetMessage("If this account exists, a password-reset email has been sent.");
    } catch (reason) {
      setError(formatSupabaseAuthError(reason));
    } finally {
      setResetBusy(false);
    }
  }

  async function resendConfirmation() {
    const client = supabaseBrowserClient();
    if (!client || !confirmationEmail) return;
    setError("");
    setConfirmationMessage("");
    setConfirmationBusy(true);
    try {
      const { error: resendError } = await client.auth.resend({
        type: "signup",
        email: confirmationEmail,
        options: { emailRedirectTo: `${window.location.origin}/vendor/login` },
      });
      if (resendError) throw resendError;
      setConfirmationMessage("Supabase accepted the resend request. Check spam; if no email arrives, the project owner needs to configure custom SMTP and review Supabase Auth email logs.");
    } catch (reason) {
      setError(formatSupabaseAuthError(reason));
    } finally {
      setConfirmationBusy(false);
    }
  }

  return <main className="auth-page">
    <section className="auth-art">
      <Link href="/" className="auth-brand"><span className="brand-symbol">V</span><span>VOLT<span className="brand-green">STOP</span></span></Link>
      <div className="auth-art-copy"><p className="eyebrow">HIGHWAY PARTNER OPERATIONS</p><h1>Keep every stop running.</h1><p>One secure entry for VoltStop operations. Your authenticated server session determines whether you open the partner workspace or the internal console.</p><div className="auth-corridor"><i/>Srikakulam <Icon name="arrow" size={15}/> Vijayawada<span className="topbar-live"><i/> Live pilot</span></div></div>
      <div className="auth-art-footer">VoltStop partner network · Andhra Pradesh</div>
    </section>
    <section className="auth-side"><div className="auth-card">
      <p className="eyebrow">VOLTSTOP ACCESS</p><h2>Sign in securely</h2><p>Use the Supabase account linked to your VoltStop role. Access is checked by the API after authentication.</p>
      <form className="auth-form" onSubmit={submit}>
        <label className="label-control">Email address<input required type="email" autoComplete="email" className="input-control" placeholder="you@yourbusiness.in" value={email} onChange={(event) => setEmail(event.target.value)}/></label>
        <label className="label-control">Password<span className="auth-password-field"><input required minLength={6} type={showPassword ? "text" : "password"} autoComplete="current-password" className="input-control" placeholder="Your account password" value={password} onChange={(event) => setPassword(event.target.value)}/><button type="button" aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword((visible) => !visible)}>{showPassword ? "Hide" : "Show"}</button></span></label>
        <button className="button button-primary auth-submit" disabled={busy || !configured}>{busy ? <><span className="spinner"/>Verifying role…</> : <>Continue securely<Icon name="arrow"/></>}</button>
      </form>
      <button type="button" className="auth-switch auth-link-button" disabled={resetBusy || !configured} onClick={() => void sendPasswordReset()}>{resetBusy ? "Sending reset email…" : "Forgot password?"}</button>
      {error && <p role="alert" className="auth-message">{error}</p>}
      {resetMessage && <p role="status" className="auth-message auth-success-message">{resetMessage}</p>}
      {confirmationEmail && <div className="auth-confirmation">
        <button type="button" className="auth-switch auth-link-button" disabled={confirmationBusy || busy || !configured} onClick={() => void resendConfirmation()}>
          {confirmationBusy ? "Sending confirmation…" : `Resend confirmation to ${confirmationEmail}`}
        </button>
        <p className="auth-hint">Supabase’s built-in email sender is restricted and rate-limited. For reliable delivery, configure a custom SMTP provider in the project’s Auth settings.</p>
      </div>}
      {confirmationMessage && <p role="status" className="auth-message auth-success-message">{confirmationMessage}</p>}
      {!configured && <div role="status" className="auth-config-warning">Supabase sign-in is unavailable. {configurationError ?? "Check the deployment configuration."}</div>}
      <p className="auth-switch">New partner? <Link href="/vendor/login">Start a vendor profile</Link></p>
      <p className="auth-switch"><Link href="/">← VoltStop home</Link></p>
    </div></section>
  </main>;
}

