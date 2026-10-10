"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import FormField from "@/components/FormField";
import Guarantee from "@/components/site/Guarantee";
import { ApiError, forgotPassword, login, loginWithCode, register, resendVerification, setToken, ssoStart } from "@/lib/api";
import type { AppConfig } from "@/lib/types";
import { emailError, type Errors, firstError, nameError, newPasswordError, passwordStrength } from "@/lib/validation";

export type AuthMode = "login" | "register" | "forgot" | "code";

interface AuthGateProps {
  config: AppConfig;
  message: string | null;
  initialMode?: AuthMode;
  onSharedToken: (token: string) => void;
  onSignedIn: () => void;
}

type Field = "name" | "email" | "password" | "code" | "token";

const FIELD_FOR_CODE: Record<string, Field> = {
  invalid_email: "email",
  email_taken: "email",
  email_not_verified: "email",
  invalid_name: "name",
  weak_password: "password",
  invalid_code: "code",
  two_factor_required: "code",
};

const proofPoints = [
  { title: "Numbers you can verify", body: "Every figure comes from SQL or Python that ran on your files, shown under the answer." },
  { title: "Private by default", body: "Isolated workspaces, API keys never written to disk, read-only database connections." },
  { title: "Ready for teams", body: "Roles, share links, two-factor sign-in, single sign-on and scheduled reports." },
];

function fieldsFor(mode: AuthMode, accounts: boolean): Field[] {
  if (!accounts) return ["token"];
  if (mode === "code") return ["code"];
  if (mode === "forgot") return ["email"];
  return mode === "register" ? ["name", "email", "password"] : ["email", "password"];
}

export default function AuthGate({ config, message, initialMode = "login", onSharedToken, onSignedIn }: AuthGateProps) {
  const accounts = config.auth_mode === "accounts";
  const startMode = initialMode === "register" && !config.registration_open ? "login" : initialMode;
  const [mode, setMode] = useState<AuthMode>(startMode);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [secret, setSecret] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] = useState("");
  const [showSecret, setShowSecret] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const [errors, setErrors] = useState<Errors<Field>>({});
  const [submitted, setSubmitted] = useState(false);
  const [formError, setFormError] = useState<string | null>(message);
  const [info, setInfo] = useState<string | null>(null);
  const [needsConfirmation, setNeedsConfirmation] = useState(false);
  const [busy, setBusy] = useState(false);
  const alertRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (formError) alertRef.current?.focus();
  }, [formError]);

  const values: Record<Field, string> = { name, email, password: secret, code, token: secret };

  function validate(field: Field, value: string): string | undefined {
    switch (field) {
      case "name":
        return nameError(value);
      case "email":
        return emailError(value);
      case "password":
        if (mode === "register") return newPasswordError(value);
        return value ? undefined : "Enter your password.";
      case "code":
        return value.trim().length >= 6 ? undefined : "Enter the 6 digit code or a recovery code.";
      case "token":
        return value.trim() ? undefined : "Enter the access token.";
    }
  }

  function change(field: Field, value: string, set: (v: string) => void) {
    set(value);
    if (submitted || errors[field]) setErrors((e) => ({ ...e, [field]: validate(field, value) }));
  }

  function switchMode(next: AuthMode) {
    setMode(next);
    setErrors({});
    setSubmitted(false);
    setFormError(null);
    setInfo(null);
    setNeedsConfirmation(false);
    setShowSecret(false);
  }

  function focusField(field: Field) {
    document.getElementById(`auth-${field}`)?.focus();
  }

  function showFailure(failure: unknown, fallback: string) {
    if (failure instanceof ApiError) {
      if (failure.code === "email_not_verified") setNeedsConfirmation(true);
      if (failure.code === "challenge_expired") {
        switchMode("login");
        setFormError(failure.message);
        return;
      }
      const field = FIELD_FOR_CODE[failure.code];
      if (field && fieldsFor(mode, accounts).includes(field)) {
        setErrors((e) => ({ ...e, [field]: failure.message }));
        focusField(field);
        return;
      }
      setFormError(failure.message);
      return;
    }
    setFormError(fallback);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    setFormError(null);
    setInfo(null);
    const fields = fieldsFor(mode, accounts);
    const found: Errors<Field> = Object.fromEntries(fields.map((f) => [f, validate(f, values[f])]));
    setErrors(found);
    const first = firstError(fields, found);
    if (first) {
      focusField(first);
      return;
    }
    if (!accounts) {
      onSharedToken(secret.trim());
      return;
    }
    setBusy(true);
    try {
      if (mode === "forgot") {
        await forgotPassword(email.trim());
        setInfo("If an account exists for that email, a reset link is on its way. The link works once and expires soon.");
        return;
      }
      if (mode === "code") {
        const done = await loginWithCode(challenge, code.trim());
        setToken(done.token as string);
        onSignedIn();
        return;
      }
      const result = mode === "login" ? await login({ email: email.trim(), password: secret }) : await register({ email: email.trim(), password: secret, name: name.trim() });
      if (result.two_factor_required && result.challenge) {
        setChallenge(result.challenge);
        setCode("");
        setSecret("");
        switchMode("code");
        return;
      }
      if (result.verification_required || !result.token) {
        switchMode("login");
        setSecret("");
        setInfo("Account created. Check your email for a confirmation link, then sign in.");
        setNeedsConfirmation(true);
        return;
      }
      setToken(result.token);
      onSignedIn();
    } catch (failure) {
      showFailure(failure, mode === "forgot" ? "Could not send the email. Please try again." : "Could not sign in. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function startSso() {
    setBusy(true);
    setFormError(null);
    try {
      const started = await ssoStart();
      window.location.assign(started.url);
    } catch (failure) {
      showFailure(failure, "Could not start single sign-on.");
      setBusy(false);
    }
  }

  async function resend() {
    const problem = emailError(email);
    if (problem) {
      setErrors((e) => ({ ...e, email: problem }));
      focusField("email");
      return;
    }
    setBusy(true);
    try {
      await resendVerification(email.trim());
      setFormError(null);
      setInfo("If that account still needs confirming, a new link was sent.");
    } catch (failure) {
      showFailure(failure, "Could not send the email.");
    } finally {
      setBusy(false);
    }
  }

  function trackCaps(event: React.KeyboardEvent<HTMLInputElement>) {
    setCapsLock(event.getModifierState?.("CapsLock") ?? false);
  }

  const forgot = mode === "forgot";
  const asking = mode === "code";
  const registering = mode === "register";
  const strength = registering && secret ? passwordStrength(secret) : null;
  const heading = !accounts ? "Enter your access token" : asking ? "Two-step verification" : forgot ? "Reset your password" : registering ? "Create your account" : "Welcome back";
  const submitLabel = !accounts ? "Continue" : asking ? "Verify and sign in" : forgot ? "Send reset link" : registering ? "Create account" : "Sign in";

  const passwordField = (
    <FormField
      id="auth-password"
      label="Password"
      error={errors.password}
      className="mt-4"
      hint={
        <>
          {capsLock && <p className="font-medium text-amber-700">Caps Lock is on.</p>}
          {strength ? (
            <div className="mt-1">
              <div aria-hidden="true" className="flex gap-1">
                {[1, 2, 3].map((n) => (
                  <span key={n} className={`h-1 flex-1 rounded-full ${strength.score >= n ? (strength.score === 3 ? "bg-emerald-500" : strength.score === 2 ? "bg-brand-500" : "bg-amber-500") : "bg-slate-200"}`} />
                ))}
              </div>
              <p className="mt-1" aria-live="polite">Strength: {strength.label}</p>
            </div>
          ) : (
            registering && <p>At least 10 characters. A short phrase of unrelated words works well.</p>
          )}
        </>
      }
    >
      {(control) => (
        <div className="relative">
          <input
            {...control}
            type={showSecret ? "text" : "password"}
            value={secret}
            onChange={(e) => change("password", e.target.value, setSecret)}
            onKeyUp={trackCaps}
            onBlur={() => setCapsLock(false)}
            autoComplete={registering ? "new-password" : "current-password"}
            maxLength={200}
            className={`${control.className} pr-16`}
          />
          <button
            type="button"
            onClick={() => setShowSecret((v) => !v)}
            aria-pressed={showSecret}
            aria-controls="auth-password"
            className="absolute right-1.5 top-1/2 mt-0.5 -translate-y-1/2 rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100"
          >
            {showSecret ? "Hide" : "Show"}
            <span className="sr-only"> password</span>
          </button>
        </div>
      )}
    </FormField>
  );

  return (
    <main className="grid min-h-screen bg-slate-50 lg:grid-cols-[1.05fr_1fr]">
      <section aria-labelledby="usp-title" className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-brand-700 via-brand-600 to-sky-600 p-12 text-white lg:flex">
        <Link href="/" className="flex w-fit items-center gap-3 rounded-lg">
          <span aria-hidden="true" className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/20 text-sm font-bold">
            DP
          </span>
          <span className="text-lg font-semibold">DataPilot</span>
        </Link>
        <div className="max-w-lg">
          <h2 id="usp-title" className="text-4xl font-semibold leading-tight">
            The AI analyst that shows its work.
          </h2>
          <p className="mt-4 text-lg text-white/85">
            Other AI tools generate numbers that look right. DataPilot computes every figure with SQL or Python on your data, shows the code, and flags anything no query produced.
          </p>
          <ul className="mt-8 space-y-4">
            {proofPoints.map((p) => (
              <li key={p.title} className="flex gap-3">
                <svg aria-hidden="true" viewBox="0 0 20 20" className="mt-0.5 h-5 w-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4.5 10.5l3.5 3.5 7.5-8" />
                </svg>
                <span>
                  <span className="font-semibold">{p.title}.</span> <span className="text-white/80">{p.body}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <Guarantee tone="brand" />
        <div aria-hidden="true" className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-white/10 blur-3xl" />
      </section>

      <div className="flex flex-col items-center justify-center px-4 py-10">
        <div className="w-full max-w-sm">
          <div className="mb-6 lg:hidden">
            <Link href="/" className="flex w-fit items-center gap-2.5 rounded-lg">
              <span aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-sky-500 text-sm font-bold text-white">
                DP
              </span>
              <span className="text-base font-semibold text-slate-900">DataPilot</span>
            </Link>
            <p className="mt-4 text-sm leading-relaxed text-slate-600">
              <span className="font-semibold text-slate-900">The AI analyst that shows its work.</span> Every number is computed by SQL or Python on your data, with the code shown.
            </p>
          </div>

          <form onSubmit={submit} noValidate aria-busy={busy} className="rounded-2xl border border-slate-200 bg-surface p-7 shadow-float">
            <h1 className="text-xl font-semibold text-slate-900">{heading}</h1>
            {accounts && !asking && !forgot && (
              <p className="mt-1 text-sm text-slate-600">
                {registering ? "Start analysing your data in minutes." : "Sign in to your workspaces."}
              </p>
            )}

            {accounts && !forgot && !asking && (
              <div className="mt-5 flex rounded-lg bg-slate-100 p-1" role="group" aria-label="Choose sign in or create account">
                {(["login", "register"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    aria-pressed={mode === m}
                    disabled={m === "register" && !config.registration_open}
                    title={m === "register" && !config.registration_open ? "Registration is closed on this server" : undefined}
                    onClick={() => switchMode(m)}
                    className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${mode === m ? "bg-surface text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"}`}
                  >
                    {m === "login" ? "Sign in" : "Create account"}
                  </button>
                ))}
              </div>
            )}

            {formError && (
              <div ref={alertRef} tabIndex={-1} role="alert" className="mt-4 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 outline-none ring-1 ring-rose-200">
                {formError}
              </div>
            )}
            {info && (
              <p role="status" className="mt-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 ring-1 ring-emerald-200">
                {info}
              </p>
            )}

            <div className="mt-2">
              {!accounts && (
                <FormField id="auth-token" label="Access token" error={errors.token} className="mt-4" hint="This server is protected by a shared access token.">
                  {(control) => (
                    <input {...control} type="password" autoComplete="off" value={secret} onChange={(e) => change("token", e.target.value, setSecret)} />
                  )}
                </FormField>
              )}

              {accounts && asking && (
                <FormField id="auth-code" label="Authentication code" error={errors.code} className="mt-4" hint="Open your authenticator app, or use one of your recovery codes.">
                  {(control) => (
                    <input
                      {...control}
                      value={code}
                      onChange={(e) => change("code", e.target.value, setCode)}
                      autoComplete="one-time-code"
                      autoFocus
                      spellCheck={false}
                      maxLength={32}
                      className={`${control.className} font-mono tracking-widest`}
                    />
                  )}
                </FormField>
              )}

              {accounts && forgot && <p className="mt-4 text-sm text-slate-600">Enter your account email and we will send a link to choose a new password.</p>}

              {accounts && registering && (
                <FormField id="auth-name" label="Name" error={errors.name} className="mt-4">
                  {(control) => <input {...control} value={name} onChange={(e) => change("name", e.target.value, setName)} autoComplete="name" maxLength={80} />}
                </FormField>
              )}

              {accounts && !asking && (
                <FormField id="auth-email" label="Email" error={errors.email} className="mt-4">
                  {(control) => (
                    <input {...control} type="email" value={email} onChange={(e) => change("email", e.target.value, setEmail)} autoComplete={registering ? "email" : "username"} maxLength={254} spellCheck={false} />
                  )}
                </FormField>
              )}

              {accounts && !forgot && !asking && passwordField}
            </div>

            {accounts && mode === "login" && config.email_enabled && (
              <div className="mt-2 text-right">
                <button type="button" onClick={() => switchMode("forgot")} className="text-sm font-medium text-brand-700 hover:underline">
                  Forgot password?
                </button>
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className="mt-5 flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-3 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
            >
              {busy && <span aria-hidden="true" className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />}
              {busy ? "Please wait..." : submitLabel}
            </button>

            {registering && (
              <p className="mt-3 text-xs leading-relaxed text-slate-500">
                By creating an account you agree to the{" "}
                <Link href="/terms" className="underline hover:text-brand-700">
                  Terms of service
                </Link>{" "}
                and acknowledge the{" "}
                <Link href="/privacy" className="underline hover:text-brand-700">
                  Privacy policy
                </Link>
                .
              </p>
            )}

            {accounts && needsConfirmation && config.email_enabled && (
              <button type="button" onClick={resend} disabled={busy} className="mt-3 w-full rounded-lg px-3 py-2 text-sm font-medium text-brand-700 ring-1 ring-brand-100 hover:bg-brand-50 disabled:opacity-40">
                Send the confirmation email again
              </button>
            )}

            {accounts && config.sso_name && mode === "login" && (
              <>
                <div className="my-5 flex items-center gap-3 text-xs text-slate-500">
                  <span className="h-px flex-1 bg-slate-200" />
                  or
                  <span className="h-px flex-1 bg-slate-200" />
                </div>
                <button type="button" onClick={startSso} disabled={busy} className="w-full rounded-lg px-3 py-2.5 text-sm font-medium text-slate-800 ring-1 ring-slate-300 hover:bg-slate-100 disabled:opacity-40">
                  Continue with {config.sso_name}
                </button>
              </>
            )}

            {(asking || forgot) && (
              <button type="button" onClick={() => switchMode("login")} className="mt-4 block w-full text-center text-sm font-medium text-brand-700 hover:underline">
                Back to sign in
              </button>
            )}
          </form>

          <p className="mt-4 text-center text-xs text-slate-500">
            {accounts ? "You stay signed in for this browser tab only." : "The token is kept in this browser tab only."}{" "}
            <Link href="/" className="font-medium text-slate-600 hover:text-brand-700 hover:underline">
              Back to home
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
