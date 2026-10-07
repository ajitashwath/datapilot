"use client";

import { useEffect, useState } from "react";
import Modal from "./Modal";
import { ApiError, twoFactorDisable, twoFactorEnable, twoFactorSetup, twoFactorStatus } from "@/lib/api";
import type { TwoFactorSetup, TwoFactorStatus } from "@/lib/types";

const inputClass = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500";
const primaryClass = "mt-4 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-40";

export default function TwoFactorDialog({ onClose }: { onClose: () => void }) {
  const [status, setStatus] = useState<TwoFactorStatus | null>(null);
  const [setup, setSetup] = useState<TwoFactorSetup | null>(null);
  const [recovery, setRecovery] = useState<string[] | null>(null);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    twoFactorStatus()
      .then(setStatus)
      .catch((failure) => setError(failure instanceof ApiError ? failure.message : "Could not load the settings."));
  }, []);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const start = (event: React.FormEvent) => {
    event.preventDefault();
    run(async () => {
      setSetup(await twoFactorSetup(password));
      setPassword("");
    });
  };

  const confirm = (event: React.FormEvent) => {
    event.preventDefault();
    run(async () => {
      const result = await twoFactorEnable(code);
      setRecovery(result.recovery_codes);
      setSetup(null);
      setCode("");
      setStatus({ available: true, enabled: true, recovery_remaining: result.recovery_codes.length });
    });
  };

  const turnOff = (event: React.FormEvent) => {
    event.preventDefault();
    run(async () => {
      await twoFactorDisable(password, code);
      setPassword("");
      setCode("");
      setStatus({ available: true, enabled: false, recovery_remaining: 0 });
    });
  };

  return (
    <Modal title="Two-factor sign-in" onClose={onClose}>
      {!status && !error && <p className="text-sm text-slate-600">Loading...</p>}
      {recovery && (
        <div>
          <p role="status" className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            Two-factor sign-in is on. Your other sessions were signed out.
          </p>
          <p className="mt-3 text-sm text-slate-700">Save these recovery codes somewhere safe. Each works once if you lose your phone. They are not shown again.</p>
          <ul className="mt-2 grid grid-cols-2 gap-1 rounded-lg bg-slate-50 p-3 font-mono text-sm text-slate-900">
            {recovery.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <button onClick={() => navigator.clipboard?.writeText(recovery.join("\n"))} className="mt-3 rounded-lg px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50">
            Copy codes
          </button>
        </div>
      )}
      {status && !status.enabled && !setup && !recovery && (
        <form onSubmit={start}>
          <p className="text-sm text-slate-700">Ask for a code from an authenticator app each time you sign in. Enter your password to begin.</p>
          <label htmlFor="tf-password" className="mt-3 block text-sm font-medium text-slate-700">
            Password
          </label>
          <input id="tf-password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} />
          <button type="submit" disabled={busy || !password} className={primaryClass}>
            Set up
          </button>
        </form>
      )}
      {setup && (
        <form onSubmit={confirm}>
          <p className="text-sm text-slate-700">Scan this with an authenticator app, or type the key by hand. Then enter the 6 digit code it shows.</p>
          <div className="mt-3 flex justify-center rounded-lg bg-white p-2 ring-1 ring-slate-200" role="img" aria-label="QR code for your authenticator app" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
          <p className="mt-2 break-all text-center font-mono text-xs text-slate-700">{setup.secret}</p>
          <label htmlFor="tf-code" className="mt-3 block text-sm font-medium text-slate-700">
            Code from the app
          </label>
          <input id="tf-code" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="one-time-code" inputMode="numeric" className={inputClass} />
          <button type="submit" disabled={busy || code.trim().length < 6} className={primaryClass}>
            Turn on
          </button>
        </form>
      )}
      {status?.enabled && !recovery && (
        <form onSubmit={turnOff}>
          <p className="text-sm text-slate-700">
            Two-factor sign-in is on. You have {status.recovery_remaining} recovery code{status.recovery_remaining === 1 ? "" : "s"} left. To turn it off, enter your password and a code.
          </p>
          <label htmlFor="tf-off-password" className="mt-3 block text-sm font-medium text-slate-700">
            Password
          </label>
          <input id="tf-off-password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} />
          <label htmlFor="tf-off-code" className="mt-3 block text-sm font-medium text-slate-700">
            Code or recovery code
          </label>
          <input id="tf-off-code" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="one-time-code" className={inputClass} />
          <button type="submit" disabled={busy || !password || code.trim().length < 6} className={primaryClass}>
            Turn off
          </button>
        </form>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-rose-700">
          {error}
        </p>
      )}
    </Modal>
  );
}
