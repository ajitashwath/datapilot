import { formatCell } from "@/lib/format";
import type { AnomalyResult } from "@/lib/types";

const severityStyle: Record<string, string> = {
  high: "bg-rose-100 text-rose-700 ring-rose-200",
  medium: "bg-amber-100 text-amber-700 ring-amber-200",
  low: "bg-sky-100 text-sky-700 ring-sky-200",
  none: "bg-emerald-100 text-emerald-700 ring-emerald-200",
};

export default function AnomalyCard({ result }: { result: AnomalyResult }) {
  const columns = result.affected_rows.length ? Object.keys(result.affected_rows[0]).slice(0, 9) : [];
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-slate-900">{result.column}</span>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{result.method}</span>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${severityStyle[result.severity]}`}>
          {result.is_anomaly ? `${result.severity} severity` : "no anomalies"}
        </span>
        {result.is_anomaly && <span className="text-xs text-slate-500">{result.total_flagged} flagged</span>}
      </div>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">{result.reason}</p>
      {columns.length > 0 && (
        <div tabIndex={0} role="region" aria-label="Affected rows" className="scroll-thin mt-3 max-h-64 overflow-auto rounded-lg border border-slate-100">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-slate-50 uppercase text-slate-500">
              <tr>
                {columns.map((c) => (
                  <th key={c} className="whitespace-nowrap px-2 py-1.5 font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {result.affected_rows.map((row, i) => (
                <tr key={i}>
                  {columns.map((c) => (
                    <td key={c} className="whitespace-nowrap px-2 py-1">
                      {formatCell(row[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
