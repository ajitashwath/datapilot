"use client";

import { useCallback, useEffect, useState } from "react";
import AccountMenu from "@/components/AccountMenu";
import AuthGate from "@/components/AuthGate";
import ChangePasswordDialog from "@/components/ChangePasswordDialog";
import TwoFactorDialog from "@/components/TwoFactorDialog";
import Chat from "@/components/Chat";
import ConnectDialog from "@/components/ConnectDialog";
import DataExplorer from "@/components/DataExplorer";
import { ScheduleDialog } from "@/components/SchedulesPanel";
import SettingsPanel from "@/components/SettingsPanel";
import Sidebar from "@/components/Sidebar";
import WorkspaceMenu from "@/components/WorkspaceMenu";
import {
  ApiError,
  addRelationship,
  clearFilters,
  clearLlm,
  createSession,
  deleteDataset,
  getConfig,
  getMe,
  getSession,
  getToken,
  listWorkspaces,
  loadSamples,
  logout,
  refreshDataset,
  resetConversation,
  setLlm,
  setToken,
  uploadFiles,
  waitForJob,
} from "@/lib/api";
import type { AppConfig, DatasetDetail, SessionState, UploadResponse, User } from "@/lib/types";

const SESSION_KEY = "datapilot-session";
let storageOwner = "anonymous";

const storageKey = () => `${SESSION_KEY}:${storageOwner}`;
type View = "analyst" | "data";

function readStoredSession(): string | null {
  try {
    return localStorage.getItem(storageKey());
  } catch {
    return null;
  }
}

function storeSession(id: string | null) {
  try {
    if (id) localStorage.setItem(storageKey(), id);
    else localStorage.removeItem(storageKey());
  } catch {
    return;
  }
}

function largestDataset(datasets: DatasetDetail[]): string | null {
  const sorted = [...datasets].sort((a, b) => b.profile.rows - a.profile.rows);
  return sorted[0]?.profile.name ?? null;
}

export default function Home() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [state, setState] = useState<SessionState | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<View>("analyst");
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState<{ kind: "error" | "info"; text: string } | null>(null);
  const [resetSignal, setResetSignal] = useState(0);
  const [login, setLogin] = useState<{ needed: boolean; message: string | null }>({ needed: false, message: null });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [scheduleSql, setScheduleSql] = useState<string | null>(null);
  const [changingPassword, setChangingPassword] = useState(false);
  const [managingTwoFactor, setManagingTwoFactor] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const accounts = config?.auth_mode === "accounts";
  const readOnly = state?.role === "reader";

  const openSession = useCallback(async (id: string) => {
    const existing = await getSession(id);
    storeSession(id);
    setSessionId(id);
    setState(existing);
    setSelected(largestDataset(existing.datasets));
    setResetSignal((n) => n + 1);
  }, []);

  const startSession = useCallback(async () => {
    const created = await createSession();
    await openSession(created.session_id);
  }, [openSession]);

  const fail = useCallback(
    (error: unknown) => {
      if (error instanceof ApiError && error.code === "unauthorized") {
        const hadToken = getToken() !== null;
        setToken(null);
        setUser(null);
        setLogin({ needed: true, message: hadToken ? "Please sign in again." : null });
        return;
      }
      if (error instanceof ApiError && error.code === "session_not_found") {
        setNotice({ kind: "info", text: "That workspace is no longer available, so a new one was started." });
        startSession().catch(() => setNotice({ kind: "error", text: "Could not start a new session." }));
        return;
      }
      setNotice({ kind: "error", text: error instanceof ApiError ? error.message : "Something went wrong. Please try again." });
    },
    [startSession],
  );

  const boot = useCallback(
    async (cfg: AppConfig) => {
      if (cfg.auth_mode === "accounts") {
        const me = await getMe();
        storageOwner = me.id;
        setUser(me);
      }
      const stored = readStoredSession();
      if (stored) {
        try {
          await openSession(stored);
          return;
        } catch (error) {
          if (!(error instanceof ApiError) || error.status !== 404) throw error;
        }
      }
      if (cfg.auth_mode === "accounts") {
        const existing = await listWorkspaces();
        if (existing.length) {
          await openSession(existing[0].session_id);
          return;
        }
      }
      await startSession();
    },
    [openSession, startSession],
  );

  useEffect(() => {
    getConfig()
      .then((cfg) => {
        setConfig(cfg);
        if (cfg.auth_required && !getToken()) {
          setLogin({ needed: true, message: null });
          return;
        }
        boot(cfg).catch(fail);
      })
      .catch(fail);
  }, [boot, fail]);

  const refresh = useCallback(async () => {
    if (!sessionId) return;
    try {
      setState(await getSession(sessionId));
    } catch (error) {
      fail(error);
    }
  }, [fail, sessionId]);

  function reportUpload(result: UploadResponse) {
    if (result.errors.length) {
      setNotice({ kind: "error", text: result.errors.map((e) => e.message).join(" ") });
    } else if (result.datasets.length) {
      setNotice({ kind: "info", text: `Loaded ${result.datasets.map((d) => d.profile.name).join(", ")}.` });
    }
    const largest = largestDataset(result.datasets);
    if (largest) setSelected(largest);
  }

  async function withUploading(work: () => Promise<UploadResponse>) {
    if (!sessionId) return;
    setUploading(true);
    try {
      const result = await work();
      await refresh();
      reportUpload(result);
    } catch (error) {
      fail(error);
    } finally {
      setUploading(false);
    }
  }

  const handleUpload = (files: File[]) => withUploading(() => uploadFiles(sessionId as string, files));
  const handleSamples = () => withUploading(() => loadSamples(sessionId as string));

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

  async function handleRefreshDataset(name: string) {
    if (!sessionId) return;
    setNotice({ kind: "info", text: `Refreshing ${name}...` });
    try {
      const { job_id } = await refreshDataset(sessionId, name);
      const job = await waitForJob(job_id);
      setNotice(job.status === "done" ? { kind: "info", text: `${name} was refreshed from its link.` } : { kind: "error", text: job.message });
      await refresh();
    } catch (error) {
      fail(error);
    }
  }

  async function handleImported(datasets: string[]) {
    await refresh();
    setNotice({ kind: "info", text: `Imported ${datasets.join(", ")}.` });
    if (datasets.length) setSelected(datasets[datasets.length - 1]);
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
    try {
      await startSession();
      setNotice({ kind: "info", text: "Started a new workspace. Upload files to begin." });
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

  async function handleSwitch(id: string) {
    try {
      await openSession(id);
    } catch (error) {
      fail(error);
    }
  }

  async function handleSignOut() {
    await logout().catch(() => undefined);
    setToken(null);
    storeSession(null);
    storageOwner = "anonymous";
    setUser(null);
    setSessionId(null);
    setState(null);
    setLogin({ needed: true, message: null });
  }

  function handleSharedToken(token: string) {
    setToken(token);
    setLogin({ needed: false, message: null });
    if (config) boot(config).catch(fail);
  }

  function handleSignedIn() {
    setLogin({ needed: false, message: null });
    if (config) boot(config).catch(fail);
  }

  if (login.needed && config) return <AuthGate config={config} message={login.message} onSharedToken={handleSharedToken} onSignedIn={handleSignedIn} />;

  const selectedProfile = state?.datasets.find((d) => d.profile.name === selected)?.profile ?? null;
  const hasLinkedData = Boolean(state?.datasets.some((d) => d.profile.source?.startsWith("url:")));

  const needsKey = config !== null && !config.llm_configured && !state?.llm;
  const navClass = (active: boolean) =>
    `flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${active ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"}`;

  return (
    <div className="flex h-screen bg-slate-50">
      {sidebarOpen && <button aria-label="Close menu" onClick={() => setSidebarOpen(false)} className="fixed inset-0 z-30 bg-black/50 md:hidden" />}
      <aside
        aria-label="Workspace"
        className={`${sidebarOpen ? "fixed inset-y-0 left-0 z-40 flex" : "hidden md:flex"} w-72 max-w-[85vw] shrink-0 flex-col border-r border-slate-200 bg-surface`}
      >
        <div className="flex items-center gap-3 px-4 pb-3 pt-4">
          <div aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-sky-500 text-sm font-bold text-white shadow-card">
            DP
          </div>
          <div>
            <h1 className="text-base font-semibold leading-tight text-slate-900">DataPilot</h1>
            <p className="text-xs text-slate-500">Verified answers from your data</p>
          </div>
        </div>
        {accounts && user && (
          <div className="px-3">
            <WorkspaceMenu
              user={user}
              state={state}
              onSwitch={handleSwitch}
              onNew={handleNewSession}
              onChanged={setState}
              onDeleted={() => {
                storeSession(null);
                if (config) boot(config).catch(fail);
              }}
              onError={(text) => setNotice({ kind: "error", text })}
            />
          </div>
        )}
        <nav aria-label="View" className="space-y-1 px-3 pt-3">
          {(["analyst", "data"] as View[]).map((v) => (
            <button
              key={v}
              onClick={() => {
                setView(v);
                setSidebarOpen(false);
              }}
              aria-pressed={view === v}
              className={navClass(view === v)}
            >
              <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                {v === "analyst" ? <path d="M3 5.5A2.5 2.5 0 0 1 5.5 3h9A2.5 2.5 0 0 1 17 5.5v6a2.5 2.5 0 0 1-2.5 2.5H9l-3.5 3v-3A2.5 2.5 0 0 1 3 11.5z" /> : <path d="M3 5h14M3 10h14M3 15h14M8 3v14" />}
              </svg>
              {v === "analyst" ? "Analyst" : "Data explorer"}
            </button>
          ))}
        </nav>
        {needsKey && (
          <button onClick={() => setSettingsOpen(true)} className="mx-3 mt-3 rounded-lg bg-amber-50 px-3 py-2 text-left text-sm font-medium text-amber-800 ring-1 ring-amber-300 hover:bg-amber-100">
            Add an API key to start asking questions
          </button>
        )}
        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-3 py-4">
          <Sidebar
            state={state}
            config={config}
            selected={selected}
            uploading={uploading}
            readOnly={readOnly}
            onSelect={(name) => {
              setSelected(name);
              setSidebarOpen(false);
            }}
            onUpload={handleUpload}
            onRemove={handleRemove}
            onLoadSamples={handleSamples}
            onConnect={() => {
              setSidebarOpen(false);
              setConnecting(true);
            }}
            onRefresh={handleRefreshDataset}
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
        </div>
        <div className="border-t border-slate-200 p-2">
          <AccountMenu
            user={accounts ? user : null}
            twoFactor={Boolean(config?.two_factor_available)}
            onSettings={() => setSettingsOpen(true)}
            onPassword={() => setChangingPassword(true)}
            onTwoFactor={() => setManagingTwoFactor(true)}
            onSignOut={handleSignOut}
          />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-3 border-b border-slate-200 bg-surface px-3 py-2 md:hidden">
          <button onClick={() => setSidebarOpen(true)} aria-label="Open menu" className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-slate-200">
            Menu
          </button>
          <span className="text-sm font-semibold text-slate-900">{state?.name ?? "DataPilot"}</span>
        </div>

        {notice && (
          <div className={`flex items-center justify-between px-5 py-2 text-sm ${notice.kind === "error" ? "bg-rose-50 text-rose-700" : "bg-brand-50 text-brand-700"}`}>
            <span role={notice.kind === "error" ? "alert" : "status"}>{notice.text}</span>
            <button onClick={() => setNotice(null)} className="font-medium underline">
              Dismiss
            </button>
          </div>
        )}

        <main className="min-h-0 min-w-0 flex-1">
          {sessionId && (
            <div className={view === "analyst" ? "h-full" : "hidden"}>
              <Chat
                sessionId={sessionId}
                dataset={selected}
                datasetCount={state?.datasets.length ?? 0}
                config={config}
                llmReady={Boolean(config?.llm_configured || state?.llm)}
                role={state?.role ?? "owner"}
                workspaceName={state?.name ?? "Analysis"}
                onSchedule={setScheduleSql}
                resetSignal={resetSignal}
                onTurnFinished={refresh}
                onLoadSamples={handleSamples}
              />
            </div>
          )}
          {sessionId && view === "data" && (
            <DataExplorer
              sessionId={sessionId}
              profile={selectedProfile ?? state?.datasets[0]?.profile ?? null}
              canEdit={!readOnly}
              minMinutes={config?.schedule_min_minutes ?? 15}
              hasLinkedData={hasLinkedData}
              emailEnabled={Boolean(config?.email_enabled)}
            />
          )}
        </main>
      </div>

      {settingsOpen && (
        <SettingsPanel
          config={config}
          sessionId={sessionId}
          llm={state?.llm ?? null}
          onSaveLlm={handleSaveLlm}
          onClearLlm={handleClearLlm}
          onClearConversation={handleClearConversation}
          onNewSession={handleNewSession}
          onClose={() => setSettingsOpen(false)}
        />
      )}
      {changingPassword && <ChangePasswordDialog onClose={() => setChangingPassword(false)} />}
      {managingTwoFactor && <TwoFactorDialog onClose={() => setManagingTwoFactor(false)} />}
      {connecting && sessionId && (
        <ConnectDialog sessionId={sessionId} allowPrivate={Boolean(config?.allow_private_connections)} onClose={() => setConnecting(false)} onImported={handleImported} />
      )}
      {scheduleSql !== null && sessionId && (
        <ScheduleDialog
          sessionId={sessionId}
          initialSql={scheduleSql}
          minMinutes={config?.schedule_min_minutes ?? 15}
          hasLinkedData={hasLinkedData}
          emailEnabled={Boolean(config?.email_enabled)}
          onClose={() => setScheduleSql(null)}
          onCreated={() => setNotice({ kind: "info", text: "Schedule created. Results appear under Data explorer, Schedules." })}
        />
      )}
    </div>
  );
}
