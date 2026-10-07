import AnomalyCard from "./AnomalyCard";
import ChartView from "./ChartView";
import CodeBlock from "./CodeBlock";
import Markdown from "./Markdown";
import { IssueList } from "./QualityPanel";
import ResultTable from "./ResultTable";
import { finalText } from "@/lib/chatState";
import type { ChatMessage, QualityIssue, Step, ToolResult } from "@/lib/types";

type ToolStep = Extract<Step, { kind: "tool" }>;

const TOOL_LABELS: Record<string, string> = {
  inspect_dataset: "Inspect dataset",
  get_schema: "Read schema",
  get_column_statistics: "Column statistics",
  execute_sql: "Run SQL",
  execute_python: "Run Python",
  create_visualization: "Build chart",
  detect_anomalies: "Detect anomalies",
  data_quality_check: "Quality check",
  compare_datasets: "Compare datasets",
  generate_summary: "Summarize dataset",
  set_context_filters: "Remember context",
};

function ToolPill({ step }: { step: ToolStep }) {
  const running = !step.result;
  const failed = step.result && !step.result.ok;
  const style = running ? "bg-brand-50 text-brand-700 ring-brand-100" : failed ? "bg-rose-50 text-rose-700 ring-rose-200" : "bg-emerald-50 text-emerald-700 ring-emerald-200";
  return (
    <span title={step.result?.error ?? undefined} className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${style}`}>
      {running ? <span className="h-2 w-2 animate-pulse rounded-full bg-brand-500" /> : <span>{failed ? "✕" : "✓"}</span>}
      {TOOL_LABELS[step.name] ?? step.name}
      {step.durationMs !== undefined && <span>{Math.round(step.durationMs)} ms</span>}
    </span>
  );
}

function Artifacts({ results }: { results: ToolResult[] }) {
  const charts = results.filter((r) => r.chart).map((r) => r.chart!);
  const anomalies = results.flatMap((r) => r.anomalies);
  const tables = results.filter((r) => r.table && !r.chart && r.anomalies.length === 0);
  const lastTable = tables[tables.length - 1]?.table;
  const quality = results.find((r) => Array.isArray(r.data.issues));
  const sqls = Array.from(new Set(results.filter((r) => r.sql).map((r) => r.sql!)));
  const codes = Array.from(new Set(results.filter((r) => r.code).map((r) => r.code!)));
  return (
    <div className="mt-3 space-y-3">
      {charts.map((chart, i) => (
        <ChartView key={i} spec={chart} />
      ))}
      {anomalies.map((a, i) => (
        <AnomalyCard key={i} result={a} />
      ))}
      {quality && <IssueList issues={quality.data.issues as QualityIssue[]} />}
      {lastTable && charts.length === 0 && <ResultTable table={lastTable} />}
      {sqls.map((sql, i) => (
        <CodeBlock key={i} label={sqls.length > 1 ? `SQL query ${i + 1}` : "SQL query"} code={sql} />
      ))}
      {codes.map((code, i) => (
        <CodeBlock key={i} label="Python code" code={code} />
      ))}
    </div>
  );
}

export default function AssistantMessage({ message, onRetry }: { message: ChatMessage; onRetry?: () => void }) {
  const toolSteps = message.steps.filter((s): s is ToolStep => s.kind === "tool");
  const answer = finalText(message);
  const results = toolSteps.flatMap((s) => (s.result?.ok ? [s.result] : []));
  const waiting = message.status === "streaming" && !answer;

  return (
    <div className="flex gap-3" role="article" aria-label="Assistant answer" aria-busy={message.status === "streaming"}>
      <div aria-hidden="true" className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-violet-500 text-xs font-bold text-white">DP</div>
      <div className="min-w-0 flex-1">
        {toolSteps.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {toolSteps.map((s) => (
              <ToolPill key={s.id} step={s} />
            ))}
          </div>
        )}
        {waiting && (
          <div role="status" aria-live="polite" className="flex items-center gap-1.5 py-2 text-slate-500">
            {[0, 1, 2].map((i) => (
              <span key={i} className="typing-dot h-2 w-2 rounded-full bg-slate-400" style={{ animationDelay: `${i * 0.15}s` }} />
            ))}
            <span className="ml-2 text-sm">{toolSteps.length ? "Analyzing" : "Thinking"}</span>
          </div>
        )}
        {answer && <Markdown text={answer} />}
        <Artifacts results={results} />
        {message.warnings.map((w, i) => (
          <p key={i} className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 ring-1 ring-amber-200">
            {w}
          </p>
        ))}
        {message.status === "error" && (
          <div role="alert" className="mt-2 flex items-start justify-between gap-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-rose-200">
            <span>{message.error}</span>
            {onRetry && (
              <button onClick={onRetry} className="shrink-0 font-medium underline">
                Retry
              </button>
            )}
          </div>
        )}
        {message.status === "done" && message.durationMs !== undefined && toolSteps.length > 0 && (
          <p className="mt-2 text-xs text-slate-500">
            Computed with {toolSteps.length} tool call{toolSteps.length === 1 ? "" : "s"} in {(message.durationMs / 1000).toFixed(1)} s
          </p>
        )}
      </div>
    </div>
  );
}
