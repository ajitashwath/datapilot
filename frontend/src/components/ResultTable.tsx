"use client";

import { useState } from "react";
import { downloadText, tableToCsv } from "@/lib/export";
import { formatCell } from "@/lib/format";
import type { TableResult } from "@/lib/types";

export default function ResultTable({ table, pageSize = 10 }: { table: TableResult; pageSize?: number }) {
  const [expanded, setExpanded] = useState(false);
  const rows = expanded ? table.rows : table.rows.slice(0, pageSize);
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <div tabIndex={0} role="region" aria-label="Result rows" className="scroll-thin max-h-96 overflow-auto">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Query result</caption>
          <thead className="sticky top-0 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              {table.columns.map((c) => (
                <th key={c} className="whitespace-nowrap px-3 py-2 font-medium">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row, i) => (
              <tr key={i} className="hover:bg-slate-50">
                {row.map((cell, j) => (
                  <td key={j} className={`whitespace-nowrap px-3 py-1.5 ${typeof cell === "number" ? "text-right tabular-nums" : ""}`}>
                    {formatCell(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50 px-3 py-1.5 text-xs text-slate-500">
        <span>
          {table.row_count} row{table.row_count === 1 ? "" : "s"}
          {table.truncated ? " (result limit reached)" : ""}
        </span>
        <button onClick={() => downloadText("result.csv", tableToCsv(table), "text/csv")} className="font-medium text-slate-600 hover:text-brand-600 hover:underline">
          Export CSV
        </button>
        {table.rows.length > pageSize && (
          <button onClick={() => setExpanded(!expanded)} className="font-medium text-brand-600 hover:underline">
            {expanded ? "Show fewer" : `Show all ${table.rows.length}`}
          </button>
        )}
      </div>
    </div>
  );
}
