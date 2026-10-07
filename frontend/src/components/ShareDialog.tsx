"use client";

import { useCallback, useEffect, useState } from "react";
import Modal from "./Modal";
import { ApiError, createShare, listShares, revokeShare } from "@/lib/api";
import type { ShareLink } from "@/lib/types";

export default function ShareDialog({ sessionId, defaultTitle, onClose }: { sessionId: string; defaultTitle: string; onClose: () => void }) {
  const [links, setLinks] = useState<ShareLink[]>([]);
  const [title, setTitle] = useState(defaultTitle);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    listShares(sessionId).then(setLinks).catch((e: Error) => setError(e.message));
  }, [sessionId]);

  useEffect(load, [load]);

  const urlFor = (token: string) => `${window.location.origin}/share/${token}`;

  async function create() {
    setBusy(true);
    setError(null);
    try {
      await createShare(sessionId, title);
      load();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not create the link.");
    } finally {
      setBusy(false);
    }
  }

  async function copy(token: string) {
    try {
      await navigator.clipboard.writeText(urlFor(token));
      setCopied(token);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      setError("Copy failed. Select the link and copy it manually.");
    }
  }

  async function revoke(token: string) {
    try {
      await revokeShare(sessionId, token);
      load();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not revoke the link.");
    }
  }

  const active = links.filter((l) => !l.revoked);
  return (
    <Modal title="Share this analysis" onClose={onClose}>
      <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 ring-1 ring-amber-200">
        Anyone with the link can read this conversation as it is now, including result tables, SQL and charts. Your uploaded datasets and API key are not shared. Later questions do not appear in an existing link.
      </p>
      <label htmlFor="share-title" className="mt-4 block text-sm font-medium text-slate-700">
        Title
      </label>
      <input id="share-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" />
      <button onClick={create} disabled={busy} className="mt-3 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-40">
        Create public link
      </button>
      {error && (
        <p role="alert" className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {error}
        </p>
      )}
      <h3 className="mt-5 text-sm font-semibold text-slate-900">Active links</h3>
      {active.length === 0 ? (
        <p className="mt-1 text-sm text-slate-500">No links yet.</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {active.map((link) => (
            <li key={link.token} className="rounded-lg border border-slate-200 p-3">
              <p className="text-sm font-medium text-slate-800">{link.title}</p>
              <input readOnly value={urlFor(link.token)} aria-label={`Link for ${link.title}`} onFocus={(e) => e.target.select()} className="mt-1 w-full rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-600" />
              <div className="mt-2 flex gap-3 text-xs font-medium">
                <button onClick={() => copy(link.token)} className="text-brand-600 hover:underline">
                  {copied === link.token ? "Copied" : "Copy link"}
                </button>
                <button onClick={() => revoke(link.token)} className="text-rose-600 hover:underline">
                  Revoke
                </button>
                <span className="ml-auto text-slate-500">{new Date(link.created_at * 1000).toLocaleDateString()}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
