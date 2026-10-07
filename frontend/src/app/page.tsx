"use client";

import { useCallback, useEffect, useState } from "react";
import Chat from "@/components/Chat";
import DataExplorer from "@/components/DataExplorer";
import SettingsPanel from "@/components/SettingsPanel";
import Sidebar from "@/components/Sidebar";
import {
  ApiError,
  addRelationship,
  clearFilters,
  clearLlm,
  createSession,
  deleteDataset,
  getConfig,
  getSession,
  loadSamples,
  resetConversation,
  setLlm,
  uploadFiles,
} from "@/lib/api";
import type { AppConfig, DatasetDetail, SessionState, UploadResponse } from "@/lib/types";

const SESSION_KEY = "datapilot-session";
type View = "analyst" | "data";

function readStoredSession(): string | null {
  try {
    return localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

function largestDataset(datasets: DatasetDetail[]): string | null {
  const sorted = [...datasets].sort((a, b) => b.profile.rows - a.profile.rows);
  return sorted[0]?.profile.name ?? null;
}

function storeSession(id: string | null) {
  try {
    if (id) localStorage.setItem(SESSION_KEY, id);
    else localStorage.removeItem(SESSION_KEY);
  } catch {
    return;
  }
}

export default function Home() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [state, setState] = useState<SessionState | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<View>("analyst");
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState<{ kind: "error" | "info"; text: string } | null>(null);
  const [resetSignal, setResetSignal] = useState(0);

  const startSession = useCallback(async () => {
    const created = await createSession();
    storeSession(created.session_id);
    setSessionId(created.session_id);
    setState(await getSession(created.session_id));
    setSelected(null);
    setResetSignal((n) => n + 1);
  }, []);

  const fail = useCallback(
    (error: unknown) => {
      if (error instanceof ApiError && error.code === "session_not_found") {
        setNotice({ kind: "info", text: "Your session expired, so a new one was started. Please upload your files again." });
        startSession().catch(() => setNotice({ kind: "error", text: "Could not start a new session." }));
        return;
      }
      setNotice({ kind: "error", text: error instanceof ApiError ? error.message : "Something went wrong. Please try again." });
    },
    [startSession],
  );

  useEffect(() => {
    getConfig().then(setConfig).catch(fail);
    async function boot() {
      const stored = readStoredSession();
      if (stored) {
        try {
          const existing = await getSession(stored);
          setSessionId(stored);
          setState(existing);
          setSelected(largestDataset(existing.datasets));
          return;
        } catch (error) {
          if (!(error instanceof ApiError) || error.status !== 404) throw error;
        }
      }
      await startSession();
    }
    boot().catch(fail);
  }, [fail, startSession]);

  const refresh = useCallback(async () => {
    if (!sessionId) return;
    try {
      setState(await getSession(sessionId));
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setNotice({ kind: "info", text: "Your session expired. A new one was started, please upload your files again." });
        await startSession();
      } else {
        fail(error);
      }
    }
  }, [fail, sessionId, startSession]);

  function reportUpload(result: UploadResponse) {
    if (result.errors.length) {
      setNotice({ kind: "error", text: result.errors.map((e) => e.message).join(" ") });
    } else if (result.datasets.length) {
      setNotice({ kind: "info", text: `Loaded ${result.datasets.map((d) => d.profile.name).join(", ")}.` });
    }
    const largest = largestDataset(result.datasets);
    if (largest) setSelected(largest);
  }

  async function handleUpload(files: File[]) {
    if (!sessionId) return;
    setUploading(true);
    try {
      const result = await uploadFiles(sessionId, files);
      await refresh();
      reportUpload(result);
    } catch (error) {
      fail(error);
    } finally {
      setUploading(false);
    }
  }

  async function handleSamples() {
    if (!sessionId) return;
    setUploading(true);
    try {
      const result = await loadSamples(sessionId);
      await refresh();
      reportUpload(result);
    } catch (error) {
      fail(error);
    } finally {
      setUploading(false);
    }
  }

  async function handleRemove(name: string) {
    if (!sessionId) return;
    try {
      const next = await deleteDataset(sessionId, name);
      setState(next);
      if (selected === name) setSelected(largestDataset(next.datasets));
    } catch (error) {
      fail(error);
    }
  }

  async function handleSaveLlm(provider: string, apiKey: string, model: string) {
    if (!sessionId) return;
    try {
      setState(await setLlm(sessionId, { provider, api_key: apiKey, model }));
      setNotice({ kind: "info", text: "API key saved for this session. It is kept in server memory only." });
    } catch (error) {
      fail(error);
    }
  }

  async function handleClearLlm() {
    if (!sessionId) return;
    try {
      setState(await clearLlm(sessionId));
    } catch (error) {
      fail(error);
    }
  }

  async function handleClearFilters() {
    if (!sessionId) return;
    try {
      setState(await clearFilters(sessionId));
    } catch (error) {
      fail(error);
    }
  }

  async function handleClearConversation() {
    if (!sessionId) return;
    try {
      setState(await resetConversation(sessionId));
      setResetSignal((n) => n + 1);
    } catch (error) {
      fail(error);
    }
  }

  async function handleNewSession() {
    const previous = sessionId;
    try {
      await startSession();
      if (previous) setNotice({ kind: "info", text: "Started a new session. Upload files to begin." });
    } catch (error) {
      fail(error);
    }
  }

  const selectedProfile = state?.datasets.find((d) => d.profile.name === selected)?.profile ?? null;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-5 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-violet-500 text-sm font-bold text-white">DP</div>
          <div>
            <h1 className="text-base font-semibold leading-tight text-slate-900">DataPilot</h1>
            <p className="text-xs text-slate-500">AI data analyst with verified computations</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <nav className="flex rounded-lg bg-slate-100 p-1">
            {(["analyst", "data"] as View[]).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`rounded-md px-3 py-1 text-sm font-medium transition ${view === v ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
              >
                {v === "analyst" ? "Analyst" : "Data explorer"}
              </button>
            ))}
          </nav>
          <SettingsPanel
            config={config}
            sessionId={sessionId}
            llm={state?.llm ?? null}
            onSaveLlm={handleSaveLlm}
            onClearLlm={handleClearLlm}
            onClearConversation={handleClearConversation}
            onNewSession={handleNewSession}
          />
        </div>
      </header>

      {notice && (
        <div className={`flex items-center justify-between px-5 py-2 text-sm ${notice.kind === "error" ? "bg-rose-50 text-rose-700" : "bg-brand-50 text-brand-700"}`}>
          <span>{notice.text}</span>
          <button onClick={() => setNotice(null)} className="font-medium underline">
            Dismiss
          </button>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <Sidebar
          state={state}
          config={config}
          selected={selected}
          uploading={uploading}
          onSelect={setSelected}
          onUpload={handleUpload}
          onRemove={handleRemove}
          onLoadSamples={handleSamples}
          onAddRelationship={async (body) => {
            if (!sessionId) return;
            try {
              await addRelationship(sessionId, body);
              await refresh();
            } catch (error) {
              fail(error);
            }
          }}
          onClearFilters={handleClearFilters}
        />
        <main className="min-w-0 flex-1">
          {sessionId && (
            <div className={view === "analyst" ? "h-full" : "hidden"}>
              <Chat
                sessionId={sessionId}
                dataset={selected}
                datasetCount={state?.datasets.length ?? 0}
                config={config}
                llmReady={Boolean(config?.llm_configured || state?.llm)}
                resetSignal={resetSignal}
                onTurnFinished={refresh}
                onLoadSamples={handleSamples}
              />
            </div>
          )}
          {sessionId && view === "data" && <DataExplorer sessionId={sessionId} profile={selectedProfile ?? state?.datasets[0]?.profile ?? null} />}
        </main>
      </div>
    </div>
  );
}
