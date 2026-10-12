"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/portal";
import { supabaseBrowserClient } from "@/services/supabase";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const client = supabaseBrowserClient();
    if (!client) {
      setError("Supabase sign-in is not configured for this deployment.");
      setReady(true);
      return () => { active = false; };
    }
    client.auth.getSession().then(({ data }) => {
      if (!active) return;
      if (!data.session) setError("This reset link is invalid or expired. Request a new one from the login page.");
      setReady(true);
    });
    return () => { active = false; };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    if (password.length < 6) {
      setError("Your new password must contain at least 6 characters.");
      return;
    }
    if (password !== confirm) {
      setError("The passwords do not match.");
      return;
    }
    const client = supabaseBrowserClient();
    if (!client) {
      setError("Supabase sign-in is not configured for this deployment.");
      return;
    }
    setBusy(true);
    try {
      const { error: updateError } = await client.auth.updateUser({ password });
      if (updateError) throw updateError;
      await client.auth.signOut();
      setMessage("Password updated. You can now sign in with your new password.");
      setTimeout(() => router.replace("/login"), 1200);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update the password.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="auth-page">
    <section className="auth-art">
      <Link href="/" className="auth-brand"><span className="brand-symbol">V</span><span>VOLT<span className="brand-green">STOP</span></span></Link>
      <div className="auth-art-copy"><p className="eyebrow">SECURE ACCOUNT RECOVERY</p><h1>Get back on the road.</h1><p>Choose a new password for your VoltStop account. Your administrator role remains protected by the API.</p><div className="auth-corridor"><i/>Supabase Auth <Icon name="arrow" size={15}/> VoltStop API<span className="topbar-live"><i/> Secure</span></div></div>
      <div className="auth-art-footer">VoltStop partner network · Andhra Pradesh</div>
    </section>
    <section className="auth-side"><div className="auth-card">
      <p className="eyebrow">VOLTSTOP ACCESS</p><h2>Set a new password</h2><p>Use at least 6 characters, then return to sign in.</p>
      <form className="auth-form" onSubmit={submit}>
        <label className="label-control">New password<input required minLength={6} type="password" autoComplete="new-password" className="input-control" value={password} onChange={(event) => setPassword(event.target.value)}/></label>
        <label className="label-control">Confirm password<input required minLength={6} type="password" autoComplete="new-password" className="input-control" value={confirm} onChange={(event) => setConfirm(event.target.value)}/></label>
        <button className="button button-primary auth-submit" disabled={busy || !ready || Boolean(error && !password)}>{busy ? <><span className="spinner"/>Updating…</> : <>Update password<Icon name="arrow"/></>}</button>
      </form>
      {error && <p role="alert" className="auth-message">{error}</p>}
      {message && <p role="status" className="auth-message auth-success-message">{message}</p>}
      <p className="auth-switch"><Link href="/login">Return to sign in</Link></p>
    </div></section>
  </main>;
}
