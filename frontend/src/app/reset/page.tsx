"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import LinkPage from "@/components/LinkPage";
import { ApiError, resetPassword } from "@/lib/api";

function Reset() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const mismatch = confirm.length > 0 && confirm !== password;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not reset the password.");
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <LinkPage title="Password changed">
        <p role="status" className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          Your password was changed and other sessions were signed out. <a href="/" className="font-medium underline">Sign in</a> with the new password.
        </p>
      </LinkPage>
    );
  }

  return (
    <LinkPage title="Choose a new password">
      <form onSubmit={submit}>
        <label htmlFor="new-password" className="text-sm font-medium text-slate-700">
          New password
        </label>
        <input id="new-password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
        <p className="mt-1 text-xs text-slate-500">At least 10 characters.</p>
        <label htmlFor="confirm-password" className="mt-3 block text-sm font-medium text-slate-700">
          Repeat the password
        </label>
        <input id="confirm-password" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
        {mismatch && <p role="alert" className="mt-1 text-sm text-rose-700">The passwords do not match.</p>}
        {error && <p role="alert" className="mt-2 text-sm text-rose-700">{error}</p>}
        <button type="submit" disabled={busy || !token || password.length < 10 || password !== confirm} className="mt-4 w-full rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-40">
          {busy ? "Please wait..." : "Change password"}
        </button>
        {!token && <p role="alert" className="mt-2 text-sm text-rose-700">This link is missing its token. Request a new one from the sign-in page.</p>}
      </form>
    </LinkPage>
  );
}

export default function ResetPage() {
  return (
    <Suspense fallback={null}>
      <Reset />
    </Suspense>
  );
}
