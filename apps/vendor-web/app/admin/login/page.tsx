"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabaseBrowserClient, supabaseBrowserConfigurationError } from "@/services/supabase";
import { Icon } from "@/components/portal";

export default function AdminLoginPage() {
  const router = useRouter();
  const supabase = supabaseBrowserClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    if (!supabase) { setError(supabaseBrowserConfigurationError() ?? "Administrator sign in is not configured."); return; }
    setBusy(true);
    const { error: authError } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    setBusy(false);
    if (authError) { setError(authError.message); return; }
    router.replace("/admin");
  }
  return <main className="admin-login-page"><div className="admin-login-glow"/><section className="admin-login-card">
    <div className="admin-login-brand"><span className="admin-brand-mark">V</span><span>VOLT<span>STOP</span><small>OPERATIONS CONSOLE</small></span></div>
    <p className="admin-login-kicker">RESTRICTED ACCESS</p><h1>Administrator sign in</h1><p className="admin-login-description">Use your VoltStop administrator account. Access is verified against server managed permissions.</p>
    <form onSubmit={submit} className="admin-login-form"><label>Email address<input type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="admin@voltstop.in"/></label><label>Password<span className="admin-password-field"><input type={showPassword ? "text" : "password"} autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter password"/><button type="button" aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword((visible) => !visible)}>{showPassword ? "Hide" : "Show"}</button></span></label>{error && <div role="alert" className="admin-login-error">{error}</div>}<button disabled={busy} type="submit">{busy ? "Verifying account…" : "Continue securely"}<Icon name="arrow" size={17}/></button></form>
    <div className="admin-login-foot"><Icon name="shield" size={15}/> Supabase session · role checks enforced by API</div>
  </section><footer>VoltStop internal use only</footer></main>;
}
