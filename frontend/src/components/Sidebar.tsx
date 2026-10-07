"use client";

import { useRef, useState } from "react";
import { scoreColor } from "@/lib/format";
import type { AppConfig, DatasetDetail, Relationship, SessionState } from "@/lib/types";

interface SidebarProps {
  state: SessionState | null;
  config: AppConfig | null;
  selected: string | null;
  uploading: boolean;
  onSelect: (name: string | null) => void;
  onUpload: (files: File[]) => void;
  onRemove: (name: string) => void;
  onLoadSamples: () => void;
  onAddRelationship: (body: { left_table: string; left_column: string; right_table: string; right_column: string }) => Promise<void>;
  onClearFilters: () => void;
  readOnly: boolean;
  onConnect: () => void;
  onRefresh: (name: string) => void;
}

function UploadZone({ onUpload, uploading, config }: { onUpload: (files: File[]) => void; uploading: boolean; config: AppConfig | null }) {
  const input = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const files = Array.from(e.dataTransfer.files);
        if (files.length) onUpload(files);
      }}
      onClick={() => input.current?.click()}
      className={`cursor-pointer rounded-xl border border-dashed px-4 py-4 text-center transition ${dragging ? "border-brand-500 bg-brand-50" : "border-slate-300 hover:border-brand-500 hover:bg-brand-50"}`}
    >
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv"
        multiple
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (files.length) onUpload(files);
          e.target.value = "";
        }}
      />
      <p className="text-sm font-medium text-slate-700">{uploading ? "Uploading and profiling..." : "Drop CSV files here"}</p>
      <p className="mt-0.5 text-xs text-slate-500">
        or click to browse{config ? `, up to ${config.max_upload_mb} MB each` : ""}
      </p>
    </div>
  );
}

function DatasetItem({ detail, active, readOnly, onSelect, onRemove, onRefresh }: { detail: DatasetDetail; active: boolean; readOnly: boolean; onSelect: () => void; onRemove: () => void; onRefresh: () => void }) {
  const p = detail.profile;
  return (
    <li
      onClick={onSelect}
      className={`group cursor-pointer rounded-xl border px-3 py-2.5 transition ${active ? "border-brand-500 bg-brand-50 shadow-card" : "border-transparent bg-surface shadow-card hover:border-slate-300"}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-semibold text-slate-800">{p.name}</span>
        <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-xs font-medium ring-1 ${scoreColor(detail.quality_score)}`} title="Data quality score">
          {detail.quality_score}
        </span>
      </div>
      <div className="mt-0.5 flex items-center justify-between text-xs text-slate-600">
        <span>
          {p.rows.toLocaleString()} rows, {p.column_count} columns{p.source ? `, ${p.source.split(":")[0]}` : ""}
        </span>
        {!readOnly && (
          <span className="flex gap-3 opacity-0 transition focus-within:opacity-100 group-hover:opacity-100">
            {p.source?.startsWith("url:") && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onRefresh();
                }}
                className="text-slate-600 hover:text-brand-600"
                aria-label={`Refresh ${p.name} from its link`}
              >
                Refresh
              </button>
            )}
            <button
              onClick={(e) => {
                e.stopPropagation();
                onRemove();
              }}
              className="text-slate-600 hover:text-rose-600"
              aria-label={`Remove ${p.name}`}
            >
              Remove
            </button>
          </span>
        )}
      </div>
    </li>
  );
}

function RelationshipRow({ r }: { r: Relationship }) {
  return (
    <li className="rounded-lg bg-surface px-3 py-2 text-xs text-slate-600 ring-1 ring-slate-200">
      <p className="font-medium text-slate-800">
        {r.left_table}.{r.left_column} <span className="text-slate-500">&rarr;</span> {r.right_table}.{r.right_column}
      </p>
      <p className="mt-0.5 text-slate-500">
        {r.cardinality}, {r.overlap_pct}% key overlap, {r.source}
      </p>
    </li>
  );
}

function RelationshipForm({ datasets, onAdd }: { datasets: DatasetDetail[]; onAdd: SidebarProps["onAddRelationship"] }) {
  const [open, setOpen] = useState(false);
  const [left, setLeft] = useState({ table: datasets[0]?.profile.name ?? "", column: "" });
  const [right, setRight] = useState({ table: datasets[1]?.profile.name ?? "", column: "" });
  const columnsOf = (table: string) => datasets.find((d) => d.profile.name === table)?.profile.columns.map((c) => c.name) ?? [];

  const picker = (value: { table: string; column: string }, set: (v: { table: string; column: string }) => void) => (
    <div className="flex gap-1.5">
      <select value={value.table} onChange={(e) => set({ table: e.target.value, column: "" })} className="w-1/2 rounded-md border border-slate-300 bg-surface px-1.5 py-1 text-xs">
        {datasets.map((d) => (
          <option key={d.profile.name}>{d.profile.name}</option>
        ))}
      </select>
      <select value={value.column} onChange={(e) => set({ ...value, column: e.target.value })} className="w-1/2 rounded-md border border-slate-300 bg-surface px-1.5 py-1 text-xs">
        <option value="">column</option>
        {columnsOf(value.table).map((c) => (
          <option key={c}>{c}</option>
        ))}
      </select>
    </div>
  );

  if (datasets.length < 2) return null;
  return (
    <div className="mt-2">
      <button onClick={() => setOpen(!open)} className="text-xs font-medium text-brand-600 hover:underline">
        {open ? "Cancel" : "Declare a join manually"}
      </button>
      {open && (
        <form
          className="mt-2 space-y-1.5"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!left.column || !right.column) return;
            await onAdd({ left_table: left.table, left_column: left.column, right_table: right.table, right_column: right.column });
            setOpen(false);
          }}
        >
          {picker(left, setLeft)}
          {picker(right, setRight)}
          <button type="submit" disabled={!left.column || !right.column} className="w-full rounded-md bg-ink py-1.5 text-xs font-medium text-white disabled:opacity-40">
            Add relationship
          </button>
        </form>
      )}
    </div>
  );
}

export default function Sidebar(props: SidebarProps) {
  const { state, config, selected, uploading, onSelect, onUpload, onRemove, onLoadSamples, onAddRelationship, onClearFilters, readOnly, onConnect, onRefresh } = props;
  const datasets = state?.datasets ?? [];
  const filters = Object.entries(state?.filters ?? {});
  return (
    <div aria-label="Datasets" role="region" className="flex flex-col gap-5">
      {!readOnly && (
        <>
          <UploadZone onUpload={onUpload} uploading={uploading} config={config} />
          <button onClick={onConnect} className="-mt-2 rounded-lg px-3 py-2 text-sm font-medium text-brand-700 hover:bg-brand-50">
            Add from a link, SQLite or Postgres
          </button>
        </>
      )}

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Datasets</h2>
          {!readOnly && config && config.sample_datasets.length > 0 && (
            <button onClick={onLoadSamples} className="text-xs font-medium text-brand-600 hover:underline">
              Load samples
            </button>
          )}
        </div>
        {datasets.length === 0 ? (
          <p className="rounded-lg bg-surface p-3 text-sm text-slate-500 ring-1 ring-slate-200">No datasets yet.</p>
        ) : (
          <ul className="space-y-2">
            {datasets.length > 1 && (
              <li
                onClick={() => onSelect(null)}
                className={`cursor-pointer rounded-xl border px-3 py-2 text-sm font-medium ${selected === null ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-200 bg-surface text-slate-600"}`}
              >
                All datasets
              </li>
            )}
            {datasets.map((d) => (
              <DatasetItem key={d.profile.name} detail={d} readOnly={readOnly} active={selected === d.profile.name} onSelect={() => onSelect(d.profile.name)} onRemove={() => onRemove(d.profile.name)} onRefresh={() => onRefresh(d.profile.name)} />
            ))}
          </ul>
        )}
      </section>

      {datasets.length > 1 && (
        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Relationships</h2>
          {state && state.relationships.length > 0 ? (
            <ul className="space-y-1.5">
              {state.relationships.map((r, i) => (
                <RelationshipRow key={i} r={r} />
              ))}
            </ul>
          ) : (
            <p className="text-xs text-slate-500">No join keys were detected automatically.</p>
          )}
          {!readOnly && <RelationshipForm datasets={datasets} onAdd={onAddRelationship} />}
        </section>
      )}

      {filters.length > 0 && (
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Conversation focus</h2>
            <button onClick={onClearFilters} className="text-xs font-medium text-brand-600 hover:underline">
              Clear
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {filters.map(([k, v]) => (
              <span key={k} className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-medium text-violet-700">
                {k}: {v}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
