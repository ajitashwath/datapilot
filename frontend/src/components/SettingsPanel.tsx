"use client";

import { useEffect, useRef, useState } from "react";
import type { AppConfig } from "@/lib/types";

interface SettingsPanelProps {
  config: AppConfig | null;
  sessionId: string | null;
  llm: { provider: string; model: string } | null;
  onSaveLlm: (provider: string, apiKey: string, model: string) => Promise<void>;
  onClearLlm: () => void;
  onClearConversation: () => void;
  onNewSession: () => void;
}

const PROVIDERS = [
  { id: "gemini", label: "Google Gemini" },
  { id: "openai", label: "OpenAI" },
];

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-800">{value}</dd>
    </div>
  );
}

function ProviderForm({ config, llm, onSave, onClear }: { config: AppConfig | null; llm: SettingsPanelProps["llm"]; onSave: SettingsPanelProps["onSaveLlm"]; onClear: () => void }) {
  const [provider, setProvider] = useState("gemini");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [saving, setSaving] = useState(false);
  const label = PROVIDERS.find((p) => p.id === llm?.provider)?.label ?? llm?.provider;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (apiKey.trim().length < 8) return;
    setSaving(true);
    await onSave(provider, apiKey.trim(), model.trim());
    setApiKey("");
    setSaving(false);
  }

  return (
    <div>
      <h2 className="mb-2 text-sm font-semibold text-slate-900">AI provider</h2>
      {llm ? (
        <div className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 ring-1 ring-emerald-200">
          <p className="font-medium">
            {label}, {llm.model}
          </p>
          <p className="text-xs">Using your key for this session.</p>
          <button onClick={onClear} className="mt-1 text-xs font-medium underline">
            Remove key
          </button>
        </div>
      ) : (
        <p className="mb-2 text-xs text-slate-500">
          {config?.llm_configured ? `Using the server default (${config.model}). Add your own key to override it.` : "Add an API key to start asking questions."}
        </p>
      )}
      <form onSubmit={submit} className="mt-2 space-y-2">
        <select aria-label="AI provider" value={provider} onChange={(e) => setProvider(e.target.value)} className="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm">
          {PROVIDERS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
        <input
          type="password"
          aria-label="API key"
          autoComplete="off"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={provider === "gemini" ? "Gemini API key" : "OpenAI API key"}
          className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-brand-500"
        />
        <input
          aria-label="Model name"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder={`Model (default ${config?.default_models[provider] ?? ""})`}
          className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-brand-500"
        />
        <button type="submit" disabled={saving || apiKey.trim().length < 8} className="w-full rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-40">
          {saving ? "Saving..." : "Save key"}
        </button>
        <p className="text-xs text-slate-500">The key is sent to the server once, kept in memory for this session only and never shown again.</p>
      </form>
    </div>
  );
}

export default function SettingsPanel({ config, sessionId, llm, onSaveLlm, onClearLlm, onClearConversation, onNewSession }: SettingsPanelProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  const needsKey = config !== null && !config.llm_configured && !llm;

  useEffect(() => {
    function close(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`rounded-lg px-3 py-1.5 text-sm font-medium ring-1 ${needsKey ? "bg-amber-50 text-amber-800 ring-amber-300" : "text-slate-600 ring-slate-200 hover:bg-slate-50"}`}
      >
        {needsKey ? "Add API key" : "Settings"}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 max-h-[80vh] w-80 space-y-4 overflow-y-auto rounded-xl border border-slate-200 bg-white p-4 shadow-xl">
          <ProviderForm config={config} llm={llm} onSave={onSaveLlm} onClear={onClearLlm} />
          <div>
            <h2 className="mb-2 text-sm font-semibold text-slate-900">Server limits</h2>
            {config ? (
              <dl className="space-y-2">
                <Row label="Upload limit" value={`${config.max_upload_mb} MB per file`} />
                <Row label="Datasets per session" value={String(config.max_files_per_session)} />
                <Row label="SQL timeout" value={`${config.sql_timeout_seconds} s`} />
                <Row label="Python timeout" value={`${config.python_timeout_seconds} s`} />
                <Row label="Rows per result" value={String(config.max_result_rows)} />
              </dl>
            ) : (
              <p className="text-sm text-slate-500">Server not reachable.</p>
            )}
          </div>
          {sessionId && <p className="truncate text-xs text-slate-500">Session {sessionId}</p>}
          <div className="flex gap-2">
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
