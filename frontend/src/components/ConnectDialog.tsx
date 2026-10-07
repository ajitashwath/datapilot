"use client";

import { useRef, useState } from "react";
import Modal from "./Modal";
import { ApiError, importFromUrl, importPostgres, importSqlite, listPostgresTables, waitForJob } from "@/lib/api";
import type { PostgresConnection } from "@/lib/types";

interface ConnectDialogProps {
  sessionId: string;
  allowPrivate: boolean;
  onClose: () => void;
  onImported: (datasets: string[]) => void;
}

const TABS = [
  { id: "url", label: "Link or Google Sheet" },
  { id: "sqlite", label: "SQLite file" },
  { id: "postgres", label: "Postgres" },
] as const;
type Tab = (typeof TABS)[number]["id"];

const inputClass = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500";
const emptyConnection: PostgresConnection = { host: "", port: 5432, dbname: "", user: "", password: "", sslmode: "require" };

export default function ConnectDialog({ sessionId, allowPrivate, onClose, onImported }: ConnectDialogProps) {
  const [tab, setTab] = useState<Tab>("url");
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [connection, setConnection] = useState<PostgresConnection>(emptyConnection);
  const [tables, setTables] = useState<string[] | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement | null>(null);

  async function run(start: () => Promise<{ job_id: string }>) {
    setBusy(true);
    setError(null);
    setStatus("Starting import...");
    try {
      const { job_id } = await start();
      const job = await waitForJob(job_id, (update) => setStatus(update.status === "running" ? "Importing and profiling..." : "Queued..."));
      if (job.status === "error") {
        setError(job.message);
        setStatus(null);
        return;
      }
      onImported(job.datasets);
      onClose();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "The import failed. Please try again.");
      setStatus(null);
    } finally {
      setBusy(false);
    }
  }

  async function loadTables() {
    setBusy(true);
    setError(null);
    try {
      const result = await listPostgresTables(sessionId, connection);
      setTables(result.tables);
      setChosen([]);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not connect.");
    } finally {
      setBusy(false);
    }
  }

  const set = <K extends keyof PostgresConnection>(key: K, value: PostgresConnection[K]) => setConnection((prev) => ({ ...prev, [key]: value }));

  return (
    <Modal title="Add data from a source" onClose={onClose} wide>
      <div className="mb-4 flex flex-wrap gap-1 rounded-lg bg-slate-100 p-1" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => {
              setTab(t.id);
              setError(null);
            }}
            className={`rounded-md px-3 py-1 text-sm font-medium ${tab === t.id ? "bg-surface text-slate-900 shadow-sm" : "text-slate-600"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "url" && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            run(() => importFromUrl(sessionId, url, name));
          }}
        >
          <label htmlFor="connect-url" className="text-sm font-medium text-slate-700">
            CSV link or Google Sheet link
          </label>
          <input id="connect-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://..." className={inputClass} />
          <p className="mt-1 text-xs text-slate-500">
            Google Sheets must be shared as "anyone with the link can view". Only https links to public servers are accepted
            {allowPrivate ? " (this server also allows private addresses)" : ""}. Linked data can be refreshed later.
          </p>
          <label htmlFor="connect-name" className="mt-3 block text-sm font-medium text-slate-700">
            Dataset name (optional)
          </label>
          <input id="connect-name" value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
          <button type="submit" disabled={busy || url.trim().length < 8} className="mt-4 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-40">
            Import
          </button>
        </form>
      )}

      {tab === "sqlite" && (
        <div>
          <p className="text-sm text-slate-600">Upload a SQLite database file. Every table and view with rows becomes a dataset, which also enables join detection between them.</p>
          <input
            ref={fileInput}
            type="file"
            accept=".db,.sqlite,.sqlite3"
            aria-label="SQLite database file"
            className="mt-3 block w-full text-sm"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) run(() => importSqlite(sessionId, file));
              event.target.value = "";
            }}
            disabled={busy}
          />
        </div>
      )}

      {tab === "postgres" && (
        <div>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              loadTables();
            }}
            className="grid gap-3 sm:grid-cols-2"
          >
            <div>
              <label htmlFor="pg-host" className="text-sm font-medium text-slate-700">
                Host
              </label>
              <input id="pg-host" value={connection.host} onChange={(e) => set("host", e.target.value)} className={inputClass} />
            </div>
            <div>
              <label htmlFor="pg-port" className="text-sm font-medium text-slate-700">
                Port
              </label>
              <input id="pg-port" type="number" value={connection.port} onChange={(e) => set("port", Number(e.target.value))} className={inputClass} />
            </div>
            <div>
              <label htmlFor="pg-db" className="text-sm font-medium text-slate-700">
                Database
              </label>
              <input id="pg-db" value={connection.dbname} onChange={(e) => set("dbname", e.target.value)} className={inputClass} />
            </div>
            <div>
              <label htmlFor="pg-ssl" className="text-sm font-medium text-slate-700">
                SSL
              </label>
              <select id="pg-ssl" value={connection.sslmode} onChange={(e) => set("sslmode", e.target.value as PostgresConnection["sslmode"])} className={inputClass}>
                <option value="verify-full">verify-full (checks the certificate)</option>
                <option value="require">require (encrypts, no certificate check)</option>
                <option value="prefer">prefer</option>
                <option value="disable">disable</option>
              </select>
            </div>
            <div>
              <label htmlFor="pg-user" className="text-sm font-medium text-slate-700">
                User
              </label>
              <input id="pg-user" value={connection.user} onChange={(e) => set("user", e.target.value)} autoComplete="off" className={inputClass} />
            </div>
            <div>
              <label htmlFor="pg-password" className="text-sm font-medium text-slate-700">
                Password
              </label>
              <input id="pg-password" type="password" value={connection.password} onChange={(e) => set("password", e.target.value)} autoComplete="off" className={inputClass} />
            </div>
            <p className="text-xs text-slate-500 sm:col-span-2">Use a read-only account. Credentials are sent once, never stored, and the connection is opened in read-only mode.</p>
            <div className="sm:col-span-2">
              <button
                type="submit"
                disabled={busy || !connection.host || !connection.dbname || !connection.user}
                className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white hover:bg-ink/80 disabled:opacity-40"
              >
                Connect and list tables
              </button>
            </div>
          </form>
          {tables && (
            <div className="mt-4">
              <p className="text-sm font-medium text-slate-700">{tables.length} tables found. Choose what to import:</p>
              <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2">
                {tables.map((table) => (
                  <li key={table}>
                    <label className="flex items-center gap-2 text-sm text-slate-700">
                      <input
                        type="checkbox"
                        checked={chosen.includes(table)}
                        onChange={(e) => setChosen((prev) => (e.target.checked ? [...prev, table] : prev.filter((t) => t !== table)))}
                      />
                      {table}
                    </label>
                  </li>
                ))}
              </ul>
              <button
                onClick={() => run(() => importPostgres(sessionId, connection, chosen))}
                disabled={busy || chosen.length === 0}
                className="mt-3 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-40"
              >
                Import {chosen.length || ""} table{chosen.length === 1 ? "" : "s"}
              </button>
            </div>
          )}
        </div>
      )}

      {status && (
        <p role="status" className="mt-3 text-sm text-slate-600">
          {status}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {error}
        </p>
      )}
    </Modal>
  );
}
