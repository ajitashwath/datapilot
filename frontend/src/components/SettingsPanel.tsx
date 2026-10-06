"use client";

import { useEffect, useRef, useState } from "react";
import type { AppConfig } from "@/lib/types";

interface SettingsPanelProps {
  config: AppConfig | null;
  sessionId: string | null;
  onClearConversation: () => void;
  onNewSession: () => void;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-800">{value}</dd>
    </div>
  );
}

export default function SettingsPanel({ config, sessionId, onClearConversation, onNewSession }: SettingsPanelProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function close(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen(!open)} className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50">
        Settings
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-80 rounded-xl border border-slate-200 bg-white p-4 shadow-xl">
          <h3 className="mb-3 text-sm font-semibold text-slate-900">Server configuration</h3>
          {config ? (
            <dl className="space-y-2">
              <Row label="Model" value={config.model} />
              <Row label="API key" value={config.llm_configured ? "configured" : "missing"} />
              <Row label="Upload limit" value={`${config.max_upload_mb} MB per file`} />
              <Row label="Datasets per session" value={String(config.max_files_per_session)} />
              <Row label="SQL timeout" value={`${config.sql_timeout_seconds} s`} />
              <Row label="Python timeout" value={`${config.python_timeout_seconds} s`} />
              <Row label="Rows per result" value={String(config.max_result_rows)} />
            </dl>
          ) : (
            <p className="text-sm text-slate-500">Server not reachable.</p>
          )}
          {sessionId && <p className="mt-3 truncate text-xs text-slate-400">Session {sessionId}</p>}
          <div className="mt-4 flex gap-2">
            <button
              onClick={() => {
                onClearConversation();
                setOpen(false);
              }}
              className="flex-1 rounded-lg bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-200"
            >
              Clear chat
            </button>
            <button
              onClick={() => {
                onNewSession();
                setOpen(false);
              }}
              className="flex-1 rounded-lg bg-rose-50 px-3 py-1.5 text-sm font-medium text-rose-700 hover:bg-rose-100"
            >
              New session
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
