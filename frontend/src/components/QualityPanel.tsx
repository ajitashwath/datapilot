"use client";

import { useEffect, useState } from "react";
import { getQuality } from "@/lib/api";
import { scoreColor } from "@/lib/format";
import type { QualityIssue, QualityReport } from "@/lib/types";

const severityStyle: Record<string, string> = {
  high: "bg-rose-100 text-rose-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-slate-100 text-slate-600",
};

export function IssueList({ issues }: { issues: QualityIssue[] }) {
  if (issues.length === 0) {
    return <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">No data quality issues were found.</p>;
  }
  return (
    <ul className="space-y-2">
      {issues.map((issue, i) => (
        <li key={i} className="flex items-start gap-3 rounded-lg border border-slate-200 bg-surface px-3 py-2">
          <span className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${severityStyle[issue.severity]}`}>{issue.severity}</span>
          <div className="min-w-0">
            <p className="text-sm text-slate-700">{issue.message}</p>
            <p className="mt-0.5 text-xs text-slate-500">{issue.type.replace(/_/g, " ")}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function QualityPanel({ sessionId, dataset }: { sessionId: string; dataset: string }) {
  const [report, setReport] = useState<QualityReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setReport(null);
    setError(null);
    getQuality(sessionId, dataset).then(setReport).catch((e: Error) => setError(e.message));
  }, [sessionId, dataset]);

  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!report) return <p className="text-sm text-slate-500">Checking data quality...</p>;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <div className={`flex h-16 w-16 items-center justify-center rounded-2xl text-2xl font-semibold ring-1 ${scoreColor(report.score)}`}>{report.score}</div>
        <div>
          <p className="font-semibold text-slate-900">Quality score</p>
          <p className="text-sm text-slate-500">
            {report.issues.length} issue{report.issues.length === 1 ? "" : "s"} detected. Checks cover missing values, duplicates, invalid types, suspicious values, constant and
            high-cardinality columns and date parsing.
          </p>
        </div>
      </div>
      <IssueList issues={report.issues} />
    </div>
  );
}
