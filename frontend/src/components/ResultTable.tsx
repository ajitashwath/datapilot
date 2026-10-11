"use client";

import { useMemo, useState } from "react";
import { downloadText, tableToCsv } from "@/lib/export";
import { formatCell } from "@/lib/format";
import type { TableResult } from "@/lib/types";

type SortState = { column: number; direction: "asc" | "desc" } | null;

function isNumericColumn(rows: unknown[][], column: number): boolean {
  let seen = false;
  for (const row of rows) {
    const cell = row[column];
    if (cell === null || cell === undefined) continue;
    if (typeof cell !== "number") return false;
    seen = true;
  }
  return seen;
}

function compareCells(a: unknown, b: unknown): number {
  const aEmpty = a === null || a === undefined;
  const bEmpty = b === null || b === undefined;
  if (aEmpty || bEmpty) return aEmpty === bEmpty ? 0 : aEmpty ? 1 : -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
}

export default function ResultTable({ table, pageSize = 10 }: { table: TableResult; pageSize?: number }) {
  const [expanded, setExpanded] = useState(false);
  const [sort, setSort] = useState<SortState>(null);

  const numeric = useMemo(() => table.columns.map((_, i) => isNumericColumn(table.rows, i)), [table]);

  const sorted = useMemo(() => {
    if (!sort) return table.rows;
    const factor = sort.direction === "asc" ? 1 : -1;
    return [...table.rows].sort((a, b) => {
      const result = compareCells(a[sort.column], b[sort.column]);
      return a[sort.column] == null || b[sort.column] == null ? result : result * factor;
    });
  }, [table.rows, sort]);

  const rows = expanded ? sorted : sorted.slice(0, pageSize);
  const total = table.rows.length;

  function toggleSort(column: number) {
    setSort((current) => {
      if (!current || current.column !== column) return { column, direction: "asc" };
      if (current.direction === "asc") return { column, direction: "desc" };
      return null;
    });
  }

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-surface">
      <div tabIndex={0} role="region" aria-label="Result rows" className="scroll-thin max-h-96 overflow-auto">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Query result</caption>
          <thead className="sticky top-0 z-10 bg-slate-50 text-xs uppercase tracking-wide text-slate-500 shadow-[inset_0_-1px_0] shadow-slate-200">
            <tr>
              {table.columns.map((c, i) => {
                const active = sort?.column === i;
                return (
                  <th
                    key={`${c}-${i}`}
                    scope="col"
                    aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
                    className={`whitespace-nowrap px-3 py-2 font-medium ${numeric[i] ? "text-right" : ""}`}
                  >
                    <button
                      type="button"
                      onClick={() => toggleSort(i)}
                      title={`Sort by ${c}`}
                      className={`inline-flex items-center gap-1 uppercase tracking-wide hover:text-slate-800 ${numeric[i] ? "flex-row-reverse" : ""} ${active ? "text-slate-800" : ""}`}
                    >
                      <span>{c}</span>
                      <span aria-hidden className={active ? "opacity-100" : "opacity-0"}>
                        {active && sort.direction === "desc" ? "↓" : "↑"}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 ? (
              <tr>
                <td colSpan={Math.max(table.columns.length, 1)} className="px-3 py-6 text-center text-slate-400">
                  No rows returned
                </td>
              </tr>
            ) : (
              rows.map((row, i) => (
                <tr key={i} className="even:bg-slate-50/40 hover:bg-brand-50/40">
                  {row.map((cell, j) => {
                    const text = formatCell(cell);
                    const empty = cell === null || cell === undefined;
                    return (
                      <td
                        key={j}
                        title={text.length > 60 ? text : undefined}
                        className={`max-w-xs truncate whitespace-nowrap px-3 py-1.5 ${numeric[j] ? "text-right tabular-nums" : ""} ${empty ? "italic text-slate-300" : "text-slate-700"}`}
                      >
                        {empty ? "null" : text}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 bg-slate-50 px-3 py-1.5 text-xs text-slate-500">
        <span aria-live="polite">
          {rows.length < total ? `Showing ${rows.length} of ` : ""}
          {table.row_count.toLocaleString("en-US")} row{table.row_count === 1 ? "" : "s"}
          {table.truncated ? " (result limit reached)" : ""}
        </span>
        <div className="flex items-center gap-3">
          {total > pageSize && (
            <button type="button" onClick={() => setExpanded(!expanded)} className="font-medium text-brand-600 hover:underline">
              {expanded ? "Show fewer" : `Show all ${total.toLocaleString("en-US")}`}
            </button>
          )}
          <button
            type="button"
            onClick={() => downloadText("result.csv", tableToCsv({ ...table, rows: sorted }), "text/csv")}
            className="font-medium text-slate-600 hover:text-brand-600 hover:underline"
          >
            Export CSV
          </button>
        </div>
      </div>
    </div>
  );
}
