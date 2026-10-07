"use client";

import { useState } from "react";

export default function TokenGate({ message, onSubmit }: { message: string | null; onSubmit: (token: string) => void }) {
  const [token, setTokenValue] = useState("");
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (token.trim()) onSubmit(token.trim());
        }}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-card"
      >
        <div className="mb-4 flex items-center gap-3">
          <div aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-violet-500 text-sm font-bold text-white">
            DP
          </div>
          <h1 className="text-lg font-semibold text-slate-900">DataPilot</h1>
        </div>
        <label htmlFor="access-token" className="text-sm font-medium text-slate-700">
          Access token
        </label>
        <input
          id="access-token"
          type="password"
          autoComplete="off"
          value={token}
          onChange={(event) => setTokenValue(event.target.value)}
          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500"
        />
        {message && (
          <p role="alert" className="mt-2 text-sm text-rose-700">
            {message}
          </p>
        )}
        <button type="submit" disabled={!token.trim()} className="mt-4 w-full rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-40">
          Continue
        </button>
        <p className="mt-3 text-xs text-slate-500">This server requires an access token. It is kept in this browser tab only.</p>
      </form>
    </main>
  );
}
