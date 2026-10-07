"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import AssistantMessage from "@/components/AssistantMessage";
import { ApiError, getShared } from "@/lib/api";
import { messagesFromTranscript } from "@/lib/chatState";
import type { ChatMessage, SharedSnapshot } from "@/lib/types";

export default function SharedAnalysis() {
  const params = useParams<{ token: string }>();
  const [snapshot, setSnapshot] = useState<SharedSnapshot | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getShared(params.token)
      .then((data) => {
        setSnapshot(data);
        setMessages(messagesFromTranscript(data.transcript));
      })
      .catch((failure) => setError(failure instanceof ApiError ? failure.message : "This link could not be opened."));
  }, [params.token]);

  return (
    <div className="min-h-screen">
      <header className="flex items-center justify-between border-b border-slate-200 bg-surface px-5 py-3">
        <div className="flex items-center gap-3">
          <div aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-sky-500 text-sm font-bold text-white">
            DP
          </div>
          <p className="text-base font-semibold text-slate-900">DataPilot</p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">Read-only shared analysis</span>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-8">
        {error && (
          <p role="alert" className="rounded-xl bg-rose-50 px-4 py-6 text-center text-rose-700 ring-1 ring-rose-200">
            {error}
          </p>
        )}
        {!snapshot && !error && <p className="text-slate-600">Loading...</p>}
        {snapshot && (
          <>
            <h1 className="text-2xl font-semibold text-slate-900">{snapshot.title}</h1>
            <p className="mt-1 text-sm text-slate-600">
              Shared on {new Date(snapshot.created_at * 1000).toLocaleDateString()}. Based on{" "}
              {snapshot.datasets.map((d) => `${d.name} (${d.rows.toLocaleString()} rows)`).join(", ") || "no datasets"}.
            </p>
            <div className="mt-6 space-y-6" role="log" aria-label="Shared conversation">
              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="flex justify-end">
                    <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-brand-600 px-4 py-2.5 text-[15px] text-white shadow-card">{m.text}</div>
                  </div>
                ) : (
                  <AssistantMessage key={m.id} message={m} />
                ),
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
