"use client";

import { useEffect, useState } from "react";
import ChartView from "./ChartView";
import QualityPanel from "./QualityPanel";
import ResultTable from "./ResultTable";
import SchedulesPanel from "./SchedulesPanel";
import { getOverview, getPreview } from "@/lib/api";
import { compactNumber, formatCell, formatNumber } from "@/lib/format";
import type { DatasetProfile, Overview, TableResult } from "@/lib/types";

const TABS = ["Overview", "Preview", "Schema", "Quality", "Schedules"] as const;
type Tab = (typeof TABS)[number];

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-card">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

function OverviewPanel({ sessionId, dataset }: { sessionId: string; dataset: string }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setOverview(null);
    setError(null);
    getOverview(sessionId, dataset).then(setOverview).catch((e: Error) => setError(e.message));
  }, [sessionId, dataset]);

  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!overview) return <p className="text-sm text-slate-500">Building overview...</p>;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Rows" value={overview.rows.toLocaleString()} />
        <Stat label="Columns" value={String(overview.columns)} />
        <Stat label="Duplicate rows" value={overview.duplicate_rows.toLocaleString()} />
        <Stat label="Quality score" value={`${overview.quality_score}/100`} />
      </div>

      {overview.key_metrics.length > 0 && (
        <section>
          <h3 className="mb-2 font-semibold text-slate-900">Key metrics</h3>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {overview.key_metrics.map((m) => (
              <Stat
                key={m.column}
                label={m.column}
                value={compactNumber(m.sum)}
                hint={`total, mean ${m.mean !== null ? formatNumber(m.mean) : "n/a"}, median ${m.median !== null ? formatNumber(m.median) : "n/a"}`}
              />
            ))}
          </div>
        </section>
      )}

      {overview.distributions.length > 0 && (
        <section>
          <h3 className="mb-2 font-semibold text-slate-900">Numerical distributions</h3>
          <div className="grid gap-3 lg:grid-cols-2">
            {overview.distributions.map((d) => (
              <ChartView
                key={d.column}
                height={220}
                spec={{
                  type: "histogram",
                  title: d.column,
                  x_label: d.column,
                  y_label: "Rows",
                  x_key: "bin",
                  y_keys: ["count"],
                  data: d.bins,
                  note: d.outliers_excluded > 0 ? `${d.outliers_excluded.toLocaleString()} values outside the 1st to 99th percentile are not shown.` : null,
                }}
              />
            ))}
          </div>
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {overview.categories.length > 0 && (
          <section>
            <h3 className="mb-2 font-semibold text-slate-900">Categorical summaries</h3>
            <div className="space-y-3">
              {overview.categories.map((c) => (
                <div key={c.column} className="rounded-xl border border-slate-200 bg-white p-4">
                  <p className="text-sm font-medium text-slate-800">
                    {c.column} <span className="font-normal text-slate-500">({c.distinct} values)</span>
                  </p>
                  <ul className="mt-2 space-y-1.5">
                    {c.top.map((t) => (
                      <li key={String(t.value)} className="text-xs text-slate-600">
                        <div className="flex justify-between">
                          <span>{String(t.value)}</span>
                          <span className="tabular-nums text-slate-500">
                            {t.count.toLocaleString()} ({t.share_pct}%)
                          </span>
                        </div>
                        <div className="mt-0.5 h-1.5 rounded-full bg-slate-100">
                          <div className="h-1.5 rounded-full bg-brand-500" style={{ width: `${t.share_pct}%` }} />
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </section>
        )}

        <section>
          <h3 className="mb-2 font-semibold text-slate-900">Missing data</h3>
          {overview.missing.length === 0 ? (
            <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">No missing values.</p>
          ) : (
            <ul className="space-y-2 rounded-xl border border-slate-200 bg-white p-4">
              {overview.missing.map((m) => (
                <li key={m.column} className="text-xs text-slate-600">
                  <div className="flex justify-between">
                    <span>{m.column}</span>
                    <span className="tabular-nums text-slate-500">
                      {m.missing.toLocaleString()} ({m.missing_pct}%)
                    </span>
                  </div>
                  <div className="mt-0.5 h-1.5 rounded-full bg-slate-100">
                    <div className="h-1.5 rounded-full bg-amber-500" style={{ width: `${Math.max(m.missing_pct, 1)}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          )}
          {overview.date_ranges.map((d) => (
            <p key={d.column} className="mt-3 text-sm text-slate-600">
              <span className="font-medium text-slate-800">{d.column}</span> spans {d.min.slice(0, 10)} to {d.max.slice(0, 10)}
            </p>
          ))}
        </section>
      </div>
    </div>
  );
}

function PreviewPanel({ sessionId, dataset }: { sessionId: string; dataset: string }) {
  const [table, setTable] = useState<TableResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTable(null);
    setError(null);
    getPreview(sessionId, dataset).then(setTable).catch((e: Error) => setError(e.message));
  }, [sessionId, dataset]);

  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!table) return <p className="text-sm text-slate-500">Loading preview...</p>;
  return <ResultTable table={table} pageSize={50} />;
}

function SchemaPanel({ profile }: { profile: DatasetProfile }) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div tabIndex={0} role="region" aria-label="Schema table" className="scroll-thin overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              {["Column", "Type", "Kind", "Missing", "Distinct", "Range or top values"].map((h) => (
                <th key={h} className="whitespace-nowrap px-3 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {profile.columns.map((c) => (
              <tr key={c.name}>
                <td className="whitespace-nowrap px-3 py-2 font-medium text-slate-800">{c.name}</td>
                <td className="px-3 py-2 font-mono text-xs text-slate-500">{c.dtype}</td>
                <td className="px-3 py-2">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{c.kind}</span>
                </td>
                <td className={`px-3 py-2 tabular-nums ${c.missing ? "text-amber-700" : "text-slate-500"}`}>{c.missing ? `${c.missing_pct}%` : "0"}</td>
                <td className="px-3 py-2 tabular-nums text-slate-600">{c.distinct.toLocaleString()}</td>
                <td className="max-w-xs truncate px-3 py-2 text-xs text-slate-500">
                  {c.kind === "numeric" || c.kind === "date"
                    ? `${formatCell(c.min)} to ${formatCell(c.max)}`
                    : c.top_values.map((t) => String(t.value)).join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function DataExplorer({
  sessionId, profile, canEdit, minMinutes, hasLinkedData,
}: { sessionId: string; profile: DatasetProfile | null; canEdit: boolean; minMinutes: number; hasLinkedData: boolean }) {
  const [tab, setTab] = useState<Tab>("Overview");
  if (!profile) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-sm text-slate-500">
        Select a dataset in the left panel to explore its overview, preview, schema and data quality.
      </div>
    );
  }
  return (
    <div className="scroll-thin h-full overflow-y-auto px-4 py-6 sm:px-8">
      <div className="mx-auto max-w-5xl">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-xl font-semibold text-slate-900">{profile.name}</h2>
            <p className="text-sm text-slate-500">
              {profile.filename}, {profile.rows.toLocaleString()} rows, {profile.column_count} columns
            </p>
          </div>
          <div className="flex rounded-lg bg-slate-100 p-1">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded-md px-3 py-1 text-sm font-medium transition ${tab === t ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"}`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
        {tab === "Overview" && <OverviewPanel sessionId={sessionId} dataset={profile.name} />}
        {tab === "Preview" && <PreviewPanel sessionId={sessionId} dataset={profile.name} />}
        {tab === "Schema" && <SchemaPanel profile={profile} />}
        {tab === "Quality" && <QualityPanel sessionId={sessionId} dataset={profile.name} />}
        {tab === "Schedules" && (
          <SchedulesPanel sessionId={sessionId} canEdit={canEdit} minMinutes={minMinutes} hasLinkedData={hasLinkedData} firstSql={`SELECT * FROM "${profile.name}" LIMIT 100`} />
        )}
      </div>
    </div>
  );
}
