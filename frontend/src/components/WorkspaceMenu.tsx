"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import TeamsDialog from "./TeamsDialog";
import { ApiError, deleteWorkspace, listTeams, listWorkspaces, updateWorkspace } from "@/lib/api";
import type { SessionState, Team, User, WorkspaceInfo } from "@/lib/types";

interface WorkspaceMenuProps {
  user: User;
  state: SessionState | null;
  onSwitch: (sessionId: string) => void;
  onNew: () => void;
  onChanged: (state: SessionState) => void;
  onDeleted: () => void;
  onError: (message: string) => void;
}

export default function WorkspaceMenu({ user, state, onSwitch, onNew, onChanged, onDeleted, onError }: WorkspaceMenuProps) {
  const [open, setOpen] = useState(false);
  const [workspaces, setWorkspaces] = useState<WorkspaceInfo[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [name, setName] = useState("");
  const [showTeams, setShowTeams] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  const isOwner = state?.role === "owner";

  const load = useCallback(() => {
    listWorkspaces().then(setWorkspaces).catch(() => setWorkspaces([]));
    listTeams().then(setTeams).catch(() => setTeams([]));
  }, []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  useEffect(() => setName(state?.name ?? ""), [state?.name]);

  useEffect(() => {
    function close(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  async function change(body: { name?: string; team_id?: string | null }) {
    if (!state) return;
    try {
      onChanged(await updateWorkspace(state.session_id, body));
      load();
    } catch (failure) {
      onError(failure instanceof ApiError ? failure.message : "Could not update the workspace.");
    }
  }

  async function remove() {
    if (!state || !window.confirm(`Delete "${state.name}" and all of its data? This cannot be undone.`)) return;
    try {
      await deleteWorkspace(state.session_id);
      setOpen(false);
      onDeleted();
    } catch (failure) {
      onError(failure instanceof ApiError ? failure.message : "Could not delete the workspace.");
    }
  }

  const adminTeams = teams.filter((t) => t.role !== "viewer");
  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="true" className="max-w-[12rem] truncate rounded-lg px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50">
        {state?.name ?? "Workspace"} <span aria-hidden="true">&#9662;</span>
      </button>
      {open && (
        <div className="absolute left-0 z-20 mt-2 max-h-[80vh] w-80 space-y-4 overflow-y-auto rounded-xl border border-slate-200 bg-white p-4 shadow-xl">
          <section aria-label="Your workspaces">
            <h2 className="mb-2 text-sm font-semibold text-slate-900">Workspaces</h2>
            <ul className="space-y-1">
              {workspaces.map((w) => (
                <li key={w.session_id}>
                  <button
                    onClick={() => {
                      setOpen(false);
                      if (w.session_id !== state?.session_id) onSwitch(w.session_id);
                    }}
                    aria-current={w.session_id === state?.session_id}
                    className={`w-full rounded-lg px-3 py-2 text-left text-sm ${w.session_id === state?.session_id ? "bg-brand-50 text-brand-700" : "hover:bg-slate-50"}`}
                  >
                    <span className="block truncate font-medium">{w.name}</span>
                    <span className="text-xs text-slate-600">
                      {w.team_name ? `${w.team_name}, ${w.role}` : "private"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <button
              onClick={() => {
                setOpen(false);
                onNew();
              }}
              className="mt-2 text-sm font-medium text-brand-600 hover:underline"
            >
              New workspace
            </button>
          </section>

          {state && (
            <section aria-label="This workspace" className="border-t border-slate-100 pt-3">
              <h2 className="mb-2 text-sm font-semibold text-slate-900">This workspace</h2>
              {isOwner ? (
                <>
                  <label htmlFor="ws-name" className="text-xs font-medium text-slate-600">
                    Name
                  </label>
                  <div className="mt-1 flex gap-2">
                    <input id="ws-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} className="min-w-0 flex-1 rounded-lg border border-slate-300 px-2 py-1 text-sm" />
                    <button onClick={() => change({ name })} disabled={!name.trim() || name === state.name} className="rounded-lg bg-slate-800 px-3 py-1 text-sm text-white disabled:opacity-40">
                      Save
                    </button>
                  </div>
                  <label htmlFor="ws-team" className="mt-3 block text-xs font-medium text-slate-600">
                    Shared with team
                  </label>
                  <select id="ws-team" value={state.team_id ?? ""} onChange={(e) => change({ team_id: e.target.value || null })} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-1 text-sm">
                    <option value="">Only me</option>
                    {adminTeams.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                  <button onClick={remove} className="mt-3 text-sm font-medium text-rose-600 hover:underline">
                    Delete workspace
                  </button>
                </>
              ) : (
                <p className="text-sm text-slate-600">You have {state.role === "reader" ? "read-only" : "edit"} access to this team workspace.</p>
              )}
            </section>
          )}
          <button onClick={() => setShowTeams(true)} className="border-t border-slate-100 pt-3 text-sm font-medium text-brand-600 hover:underline">
            Manage teams
          </button>
        </div>
      )}
      {showTeams && <TeamsDialog user={user} onClose={() => setShowTeams(false)} onChanged={load} />}
    </div>
  );
}
