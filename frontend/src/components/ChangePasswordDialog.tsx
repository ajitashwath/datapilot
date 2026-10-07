"use client";

import { useState } from "react";
import Modal from "./Modal";
import { ApiError, changePassword } from "@/lib/api";

const inputClass = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500";

export default function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await changePassword(current, next);
      setDone(true);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not change the password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Change password" onClose={onClose}>
      {done ? (
        <p role="status" className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          Your password was changed. Your other sessions were signed out and a confirmation email was sent if email is set up.
        </p>
      ) : (
        <form onSubmit={submit}>
          <label htmlFor="pw-current" className="text-sm font-medium text-slate-700">
            Current password
          </label>
          <input id="pw-current" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} className={inputClass} />
          <label htmlFor="pw-new" className="mt-3 block text-sm font-medium text-slate-700">
            New password
          </label>
          <input id="pw-new" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} className={inputClass} />
          <p className="mt-1 text-xs text-slate-500">At least 10 characters.</p>
          <label htmlFor="pw-repeat" className="mt-3 block text-sm font-medium text-slate-700">
            Repeat the new password
          </label>
          <input id="pw-repeat" type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} className={inputClass} />
          {repeat && repeat !== next && (
            <p role="alert" className="mt-1 text-sm text-rose-700">
              The passwords do not match.
            </p>
          )}
          {error && (
            <p role="alert" className="mt-2 text-sm text-rose-700">
              {error}
            </p>
          )}
          <button type="submit" disabled={busy || !current || next.length < 10 || next !== repeat} className="mt-4 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-40">
            Change password
          </button>
        </form>
      )}
    </Modal>
  );
}
