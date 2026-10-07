"use client";

import { useState } from "react";
import { ApiError, forgotPassword, login, loginWithCode, register, resendVerification, setToken, ssoStart } from "@/lib/api";
import type { AppConfig } from "@/lib/types";

interface AuthGateProps {
  config: AppConfig;
  message: string | null;
  onSharedToken: (token: string) => void;
  onSignedIn: () => void;
}

type Mode = "login" | "register" | "forgot" | "code";

const inputClass = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500";

export default function AuthGate({ config, message, onSharedToken, onSignedIn }: AuthGateProps) {
  const accounts = config.auth_mode === "accounts";
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [needsConfirmation, setNeedsConfirmation] = useState(false);
  const [challenge, setChallenge] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const shown = error ?? message;

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
    setInfo(null);
    setNeedsConfirmation(false);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setInfo(null);
    if (!accounts) {
      if (secret.trim()) onSharedToken(secret.trim());
      return;
    }
    setBusy(true);
    try {
      if (mode === "forgot") {
        await forgotPassword(email);
        setInfo("If an account exists for that email, a reset link is on its way. The link works once and expires soon.");
        return;
      }
      if (mode === "code") {
        const done = await loginWithCode(challenge, code);
        setToken(done.token as string);
        onSignedIn();
        return;
      }
      const result = mode === "login" ? await login({ email, password: secret }) : await register({ email, password: secret, name });
      if (result.two_factor_required && result.challenge) {
        setChallenge(result.challenge);
        setCode("");
        setSecret("");
        setMode("code");
        return;
      }
      if (result.verification_required || !result.token) {
        setInfo("Account created. Check your email for a confirmation link, then sign in.");
        setNeedsConfirmation(true);
        setMode("login");
        setSecret("");
        return;
      }
      setToken(result.token);
      onSignedIn();
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === "email_not_verified") setNeedsConfirmation(true);
      if (failure instanceof ApiError && failure.code === "challenge_expired") {
        setMode("login");
        setCode("");
      }
      setError(failure instanceof ApiError ? failure.message : "Could not sign in. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function startSso() {
    setBusy(true);
    setError(null);
    try {
      const started = await ssoStart();
      window.location.assign(started.url);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not start single sign-on.");
      setBusy(false);
    }
  }

  async function resend() {
    setBusy(true);
    try {
      await resendVerification(email);
      setError(null);
      setInfo("If that account still needs confirming, a new link was sent.");
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not send the email.");
    } finally {
      setBusy(false);
    }
  }

  const forgot = mode === "forgot";
  const asking = mode === "code";
  const ready = accounts ? (asking ? code.trim().length >= 6 : forgot ? email.trim().length > 3 : Boolean(secret.trim() && email.trim())) : Boolean(secret.trim());
  const submitLabel = !accounts ? "Continue" : asking ? "Verify and sign in" : forgot ? "Send reset link" : mode === "login" ? "Sign in" : "Create account";

  return (
    <main className="grid min-h-screen lg:grid-cols-2">
      <section aria-hidden="true" className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-brand-700 via-brand-600 to-sky-600 p-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/20 text-sm font-bold">DP</div>
          <span className="text-lg font-semibold">DataPilot</span>
        </div>
        <div>
          <p className="text-4xl font-semibold leading-tight">Ask your data a question. Get an answer you can check.</p>
          <p className="mt-4 max-w-md text-white/80">Every number comes from SQL or Python that ran on your files, with the code shown right under the answer.</p>
        </div>
        <ul className="space-y-2 text-sm text-white/80">
          <li>Charts, anomalies and joins across your CSVs</li>
          <li>Private workspaces, teams and share links</li>
          <li>Scheduled queries with email and webhook alerts</li>
        </ul>
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-white/10 blur-3xl" />
      </section>
      <div className="flex items-center justify-center px-4 py-10">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl border border-slate-200 bg-surface p-7 shadow-float">
        <div className="mb-4 flex items-center gap-3">
          <div aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-sky-500 text-sm font-bold text-white">
            DP
          </div>
          <h1 className="text-lg font-semibold text-slate-900">Sign in to DataPilot</h1>
        </div>
        {accounts ? (
          <>
            {!forgot && !asking && (
              <div className="mb-3 flex rounded-lg bg-slate-100 p-1" role="tablist">
                {(["login", "register"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    role="tab"
                    aria-selected={mode === m}
                    disabled={m === "register" && !config.registration_open}
                    onClick={() => switchMode(m)}
                    className={`flex-1 rounded-md px-3 py-1 text-sm font-medium disabled:opacity-40 ${mode === m ? "bg-surface text-slate-900 shadow-sm" : "text-slate-600"}`}
                  >
                    {m === "login" ? "Sign in" : "Create account"}
                  </button>
                ))}
              </div>
            )}
            {forgot && <p className="mb-3 text-sm text-slate-600">Enter your email and we will send a link to choose a new password.</p>}
            {asking && (
              <>
                <p className="mb-3 text-sm text-slate-600">Enter the 6 digit code from your authenticator app, or one of your recovery codes.</p>
                <label htmlFor="auth-code" className="text-sm font-medium text-slate-700">
                  Code
                </label>
                <input id="auth-code" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="one-time-code" inputMode="text" autoFocus className={inputClass} />
              </>
            )}
            {mode === "register" && (
              <>
                <label htmlFor="auth-name" className="text-sm font-medium text-slate-700">
                  Name
                </label>
                <input id="auth-name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" className={inputClass} />
              </>
            )}
            {!asking && (
              <>
                <label htmlFor="auth-email" className="mt-3 block text-sm font-medium text-slate-700">
                  Email
                </label>
                <input id="auth-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" className={inputClass} />
              </>
            )}
            {!forgot && !asking && (
              <>
                <label htmlFor="auth-password" className="mt-3 block text-sm font-medium text-slate-700">
                  Password
                </label>
                <input
                  id="auth-password"
                  type="password"
                  value={secret}
                  onChange={(e) => setSecret(e.target.value)}
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  className={inputClass}
                />
                {mode === "register" && <p className="mt-1 text-xs text-slate-500">At least 10 characters.</p>}
              </>
            )}
          </>
        ) : (
          <>
            <label htmlFor="access-token" className="text-sm font-medium text-slate-700">
              Access token
            </label>
            <input id="access-token" type="password" autoComplete="off" value={secret} onChange={(e) => setSecret(e.target.value)} className={inputClass} />
          </>
        )}
        {shown && (
          <p role="alert" className="mt-2 text-sm text-rose-700">
            {shown}
          </p>
        )}
        {info && (
          <p role="status" className="mt-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            {info}
          </p>
        )}
        <button type="submit" disabled={busy || !ready} className="mt-4 w-full rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-40">
          {busy ? "Please wait..." : submitLabel}
        </button>
        {accounts && needsConfirmation && config.email_enabled && (
          <button type="button" onClick={resend} disabled={busy || !email.trim()} className="mt-2 w-full rounded-lg px-3 py-2 text-sm font-medium text-brand-700 ring-1 ring-brand-100 hover:bg-brand-50 disabled:opacity-40">
            Send the confirmation email again
          </button>
        )}
        {accounts && config.sso_name && mode === "login" && (
          <>
            <div className="my-4 flex items-center gap-3 text-xs text-slate-500">
              <span className="h-px flex-1 bg-slate-200" />
              or
              <span className="h-px flex-1 bg-slate-200" />
            </div>
            <button type="button" onClick={startSso} disabled={busy} className="w-full rounded-lg px-3 py-2 text-sm font-medium text-slate-800 ring-1 ring-slate-300 hover:bg-slate-100 disabled:opacity-40">
              Continue with {config.sso_name}
            </button>
          </>
        )}
        {asking && (
          <button type="button" onClick={() => switchMode("login")} className="mt-3 block w-full text-center text-sm font-medium text-brand-700 hover:underline">
            Back to sign in
          </button>
        )}
        {accounts && config.email_enabled && !asking && (
          <button type="button" onClick={() => switchMode(forgot ? "login" : "forgot")} className="mt-3 block w-full text-center text-sm font-medium text-brand-700 hover:underline">
            {forgot ? "Back to sign in" : "Forgot your password?"}
          </button>
        )}
        <p className="mt-3 text-xs text-slate-500">
          {accounts ? "Your session token is kept in this browser tab only." : "This server requires an access token. It is kept in this browser tab only."}
        </p>
      </form>
      </div>
    </main>
  );
}
