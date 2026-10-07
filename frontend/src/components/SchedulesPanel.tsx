"use client";

import { useCallback, useEffect, useState } from "react";
import Modal from "./Modal";
import ResultTable from "./ResultTable";
import { ApiError, createSchedule, deleteSchedule, getScheduleRuns, listSchedules, runScheduleNow, toggleSchedule } from "@/lib/api";
import type { Schedule, ScheduleRun } from "@/lib/types";

const INTERVALS = [
  { label: "Every hour", minutes: 60 },
  { label: "Every 6 hours", minutes: 360 },
  { label: "Every day", minutes: 1440 },
  { label: "Every week", minutes: 10080 },
];

const inputClass = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500";

export function ScheduleDialog({
  sessionId, initialSql, minMinutes, hasLinkedData, onClose, onCreated,
}: { sessionId: string; initialSql: string; minMinutes: number; hasLinkedData: boolean; onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [sql, setSql] = useState(initialSql);
  const [minutes, setMinutes] = useState(1440);
  const [refresh, setRefresh] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const options = INTERVALS.filter((i) => i.minutes >= minMinutes);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createSchedule(sessionId, { name, sql, every_minutes: minutes, refresh_sources: refresh });
      onCreated();
      onClose();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not create the schedule.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Schedule this query" onClose={onClose} wide>
      <form onSubmit={submit}>
        <label htmlFor="schedule-name" className="text-sm font-medium text-slate-700">
          Name
        </label>
        <input id="schedule-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} className={inputClass} />
        <label htmlFor="schedule-sql" className="mt-3 block text-sm font-medium text-slate-700">
          SQL (read-only SELECT)
        </label>
        <textarea id="schedule-sql" value={sql} onChange={(e) => setSql(e.target.value)} rows={5} className={`${inputClass} font-mono text-xs`} />
        <label htmlFor="schedule-every" className="mt-3 block text-sm font-medium text-slate-700">
          Repeat
        </label>
        <select id="schedule-every" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} className={inputClass}>
          {options.map((o) => (
            <option key={o.minutes} value={o.minutes}>
              {o.label}
            </option>
          ))}
        </select>
        {hasLinkedData && (
          <label className="mt-3 flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={refresh} onChange={(e) => setRefresh(e.target.checked)} />
            Re-download linked datasets before each run
          </label>
        )}
        <p className="mt-2 text-xs text-slate-500">Results are stored (last 20 runs) and shown here. No emails are sent.</p>
        {error && (
          <p role="alert" className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy || !name.trim() || !sql.trim()} className="mt-4 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-40">
          Create schedule
        </button>
      </form>
    </Modal>
  );
}

function RunView({ run }: { run: ScheduleRun }) {
  return (
    <div className="mt-2">
      <p className="text-xs text-slate-500">
        {new Date(run.ran_at * 1000).toLocaleString()} {run.note ? `, ${run.note}` : ""}
      </p>
      {run.ok ? (
        <ResultTable table={{ columns: run.columns, rows: run.rows, row_count: run.row_count, truncated: false }} pageSize={5} />
      ) : (
        <p role="alert" className="mt-1 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {run.error}
        </p>
      )}
    </div>
  );
}

export default function SchedulesPanel({
  sessionId, canEdit, minMinutes, hasLinkedData, firstSql,
}: { sessionId: string; canEdit: boolean; minMinutes: number; hasLinkedData: boolean; firstSql: string }) {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [runs, setRuns] = useState<ScheduleRun[]>([]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    listSchedules(sessionId).then(setSchedules).catch((e: Error) => setError(e.message));
  }, [sessionId]);

  useEffect(load, [load]);

  async function show(id: string) {
    setOpen(open === id ? null : id);
    if (open !== id) setRuns(await getScheduleRuns(sessionId, id).catch(() => []));
  }

  async function act(work: () => Promise<unknown>) {
    setError(null);
    try {
      await work();
      load();
      if (open) setRuns(await getScheduleRuns(sessionId, open).catch(() => []));
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "That did not work. Please try again.");
    }
  }

  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-slate-600">Saved queries that run on their own and keep their latest results. Use "Schedule" under any SQL block in the chat, or create one here.</p>
        {canEdit && (
          <button onClick={() => setCreating(true)} className="shrink-0 rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700">
            New schedule
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {error}
        </p>
      )}
      {schedules.length === 0 ? (
        <p className="mt-4 rounded-lg bg-white p-4 text-sm text-slate-500 ring-1 ring-slate-200">No schedules yet.</p>
      ) : (
        <ul className="mt-4 space-y-3">
          {schedules.map((s) => (
            <li key={s.id} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-medium text-slate-900">{s.name}</p>
                  <p className="text-xs text-slate-500">
                    Every {s.every_minutes >= 1440 ? `${Math.round(s.every_minutes / 1440)} day(s)` : `${Math.round(s.every_minutes / 60)} hour(s)`}
                    {s.refresh_sources ? ", refreshes linked data" : ""}, {s.enabled ? `next ${new Date(s.next_run_at * 1000).toLocaleString()}` : "paused"}
                  </p>
                </div>
                <div className="flex items-center gap-3 text-xs font-medium">
                  <span className={`rounded-full px-2 py-0.5 ${s.last_run ? (s.last_run.ok ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700") : "bg-slate-100 text-slate-600"}`}>
                    {s.last_run ? (s.last_run.ok ? "last run ok" : "last run failed") : "not run yet"}
                  </span>
                  <button onClick={() => show(s.id)} className="text-brand-600 hover:underline" aria-expanded={open === s.id}>
                    {open === s.id ? "Hide results" : "Results"}
                  </button>
                  {canEdit && (
                    <>
                      <button onClick={() => act(() => runScheduleNow(sessionId, s.id))} className="text-slate-700 hover:underline">
                        Run now
                      </button>
                      <button onClick={() => act(() => toggleSchedule(sessionId, s.id, !s.enabled))} className="text-slate-700 hover:underline">
                        {s.enabled ? "Pause" : "Resume"}
                      </button>
                      <button onClick={() => act(() => deleteSchedule(sessionId, s.id))} className="text-rose-600 hover:underline">
                        Delete
                      </button>
                    </>
                  )}
                </div>
              </div>
              <pre tabIndex={0} aria-label="Scheduled SQL" className="scroll-thin mt-2 overflow-x-auto rounded-lg bg-slate-900 p-2 text-xs text-slate-100">
                <code>{s.sql}</code>
              </pre>
              {open === s.id && (runs.length ? runs.slice(0, 3).map((run) => <RunView key={run.id} run={run} />) : <p className="mt-2 text-sm text-slate-500">No runs yet.</p>)}
            </li>
          ))}
        </ul>
      )}
      {creating && <ScheduleDialog sessionId={sessionId} initialSql={firstSql} minMinutes={minMinutes} hasLinkedData={hasLinkedData} onClose={() => setCreating(false)} onCreated={load} />}
    </div>
  );
}
