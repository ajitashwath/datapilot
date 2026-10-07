"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AssistantMessage from "./AssistantMessage";
import ShareDialog from "./ShareDialog";
import { ApiError, getOverview, getTranscript, streamChat } from "@/lib/api";
import { applyEvent, messagesFromTranscript, newAssistantMessage } from "@/lib/chatState";
import { buildReport, downloadText } from "@/lib/export";
import type { AppConfig, ChatMessage } from "@/lib/types";

interface ChatProps {
  sessionId: string;
  dataset: string | null;
  datasetCount: number;
  config: AppConfig | null;
  llmReady: boolean;
  role: string;
  workspaceName: string;
  onSchedule: (sql: string) => void;
  resetSignal: number;
  onTurnFinished: () => void;
  onLoadSamples: () => void;
  usingSharedKey: boolean;
  onOpenSettings: () => void;
}

const CAPABILITIES = [
  { title: "Ask in plain English", text: "Rankings, trends, comparisons and averages computed by SQL on your data." },
  { title: "See the work", text: "Every answer shows the SQL or Python that produced it." },
  { title: "Spot anomalies", text: "IQR, z-score and time series checks with a computed explanation." },
  { title: "Join your files", text: "Relationships between uploaded CSVs are detected and used safely." },
];

let counter = 0;
const nextId = () => `m${Date.now()}-${counter++}`;

export default function Chat({ sessionId, dataset, datasetCount, config, llmReady, role, workspaceName, onSchedule, resetSignal, onTurnFinished, onLoadSamples, usingSharedKey, onOpenSettings }: ChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [sharing, setSharing] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    abortRef.current?.abort();
    setBusy(false);
    getTranscript(sessionId)
      .then((entries) => setMessages(messagesFromTranscript(entries)))
      .catch(() => setMessages([]));
  }, [sessionId, resetSignal]);

  useEffect(() => {
    setSuggestions([]);
    if (!dataset) return;
    getOverview(sessionId, dataset)
      .then((o) => setSuggestions(o.suggested_questions.slice(0, 6)))
      .catch(() => setSuggestions([]));
  }, [sessionId, dataset]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const send = useCallback(
    async (question: string) => {
      const text = question.trim();
      if (!text || busy) return;
      const assistantId = nextId();
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "user", text, steps: [], status: "done", warnings: [] },
        newAssistantMessage(assistantId),
      ]);
      setInput("");
      setBusy(true);
      const controller = new AbortController();
      abortRef.current = controller;
      const update = (fn: (m: ChatMessage) => ChatMessage) =>
        setMessages((prev) => prev.map((m) => (m.id === assistantId ? fn(m) : m)));
      try {
        await streamChat(sessionId, text, dataset, (event) => update((m) => applyEvent(m, event)), controller.signal);
        update((m) => (m.status === "streaming" ? (controller.signal.aborted ? { ...m, status: "done" } : applyEvent(m, { type: "error", message: "The connection ended before the answer was complete." })) : m));
      } catch (error) {
        const message = error instanceof ApiError ? error.message : "Something went wrong while contacting the server.";
        update((m) => applyEvent(m, { type: "error", message }));
      } finally {
        setBusy(false);
        onTurnFinished();
      }
    },
    [busy, dataset, onTurnFinished, sessionId],
  );

  const retry = useCallback(
    (index: number) => {
      const question = messages[index - 1]?.text;
      if (question) send(question);
    },
    [messages, send],
  );

  const canEdit = role !== "reader";
  const blocked = datasetCount === 0 || !llmReady || !canEdit;

  return (
    <div className="flex h-full flex-col">
      <div className={`scroll-thin flex-1 overflow-y-auto px-4 py-6 sm:px-8 ${messages.length === 0 ? "hero-glow" : ""}`}>
        <div className="mx-auto max-w-3xl space-y-6" role="log" aria-label="Conversation" aria-live="polite">
          {messages.length > 0 && !busy && (
            <div className="flex justify-end gap-2">
              {role === "owner" && (
                <button onClick={() => setSharing(true)} className="rounded-lg px-3 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-surface">
                  Share
                </button>
              )}
              <button
                onClick={() => downloadText("datapilot-report.md", buildReport(messages, dataset ? `Analysis of ${dataset}` : "Analysis report"), "text/markdown")}
                className="rounded-lg px-3 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-surface"
              >
                Export report
              </button>
            </div>
          )}
          {messages.length === 0 && (
            <div className="pt-8 sm:pt-14">
              {datasetCount === 0 ? (
                <div className="rounded-3xl border border-slate-200 bg-surface p-10 text-center shadow-card">
                  <div aria-hidden="true" className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
                    <svg viewBox="0 0 20 20" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M4 16V9m4 7V4m4 12v-5m4 5V7" />
                    </svg>
                  </div>
                  <h2 className="mt-4 text-2xl font-semibold text-slate-900">Start by adding some data</h2>
                  <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">
                    Drop one or more CSV files into the panel on the left, or try the bundled sales, customers and products sample data.
                  </p>
                  {config && config.sample_datasets.length > 0 && (
                    <button onClick={onLoadSamples} className="mt-6 rounded-xl bg-brand-600 px-5 py-2.5 text-sm font-medium text-white shadow-card hover:bg-brand-700">
                      Load sample data
                    </button>
                  )}
                </div>
              ) : (
                <div>
                  <h2 className="bg-gradient-to-r from-slate-900 to-brand-500 bg-clip-text text-3xl font-semibold text-transparent sm:text-4xl">What would you like to know?</h2>
                  <p className="mt-2 text-sm text-slate-500">
                    Answers are computed on your real data with SQL and Python. Currently focused on <span className="font-medium text-slate-700">{dataset ?? "all datasets"}</span>.
                  </p>
                  <div className="mt-5 grid gap-2 sm:grid-cols-2">
                    {suggestions.map((q) => (
                      <button
                        key={q}
                        onClick={() => send(q)}
                        disabled={blocked}
                        className="group flex items-start justify-between gap-3 rounded-2xl border border-slate-200 bg-surface px-4 py-3.5 text-left text-sm text-slate-700 shadow-card transition hover:-translate-y-0.5 hover:border-brand-500 hover:shadow-float disabled:opacity-50"
                      >
                        <span>{q}</span>
                        <span aria-hidden="true" className="text-slate-400 transition group-hover:translate-x-0.5 group-hover:text-brand-600">
                          &rarr;
                        </span>
                      </button>
                    ))}
                  </div>
                  <div className="mt-10 grid gap-3 sm:grid-cols-2">
                    {CAPABILITIES.map((c) => (
                      <div key={c.title} className="rounded-2xl bg-surface/60 p-4 ring-1 ring-slate-200">
                        <p className="text-sm font-semibold text-slate-800">{c.title}</p>
                        <p className="mt-1 text-sm text-slate-500">{c.text}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={m.id} className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-gradient-to-br from-brand-600 to-brand-700 px-4 py-2.5 text-[15px] text-white shadow-card">{m.text}</div>
              </div>
            ) : (
              <AssistantMessage key={m.id} message={m} onRetry={() => retry(i)} onSchedule={canEdit ? onSchedule : undefined} />
            ),
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="bg-gradient-to-t from-slate-50 via-slate-50 to-transparent px-4 pb-4 pt-2 sm:px-8">
        <div className="mx-auto max-w-3xl">
          {!canEdit && (
            <p className="mb-2 rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700">You have read-only access to this workspace, so asking new questions is disabled.</p>
          )}
          {config && !llmReady && canEdit && (
            <p className="mb-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 ring-1 ring-amber-200">
              No LLM API key yet. Open Settings and add a Gemini or OpenAI API key to ask questions.
            </p>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="flex items-end gap-2 rounded-3xl border border-slate-200 bg-surface p-2 pl-4 shadow-float focus-within:border-brand-500"
          >
            <textarea
              aria-label="Ask a question about your data"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              rows={1}
              maxLength={2000}
              disabled={blocked}
              placeholder={!canEdit ? "Read-only workspace" : datasetCount === 0 ? "Upload a CSV to start asking questions" : "Ask a question about your data"}
              className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-[15px] outline-none focus-visible:outline-none placeholder:text-slate-500 disabled:cursor-not-allowed"
            />
            {busy ? (
              <button type="button" onClick={() => abortRef.current?.abort()} className="rounded-xl bg-ink px-4 py-2 text-sm font-medium text-white hover:bg-ink/80">
                Stop
              </button>
            ) : (
              <button type="submit" disabled={blocked || !input.trim()} className="rounded-2xl bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-40">
                Ask
              </button>
            )}
          </form>
          {usingSharedKey && canEdit && (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-100 px-4 py-2.5 text-sm text-slate-700">
              <span>You are using the shared Gemini key, which has a daily limit. Bring your own key for uninterrupted answers.</span>
              <button onClick={onOpenSettings} className="rounded-lg bg-surface px-3 py-1.5 text-sm font-medium text-brand-700 shadow-card hover:bg-brand-50">
                Use my own key
              </button>
            </div>
          )}
          <p className="mt-2 text-center text-xs text-slate-500">Numbers come from executed queries. Check the SQL or code under each answer.</p>
        </div>
      </div>
      {sharing && <ShareDialog sessionId={sessionId} defaultTitle={workspaceName} onClose={() => setSharing(false)} />}
    </div>
  );
}
