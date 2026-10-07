"use client";

import { useState } from "react";

export default function CodeBlock({ label, code }: { label: string; code: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <details className="group rounded-lg border border-slate-200 bg-white">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-sm font-medium text-slate-600 hover:text-slate-900">
        <span className="text-slate-500 transition group-open:rotate-90">&#9656;</span>
        {label}
      </summary>
      <div className="relative border-t border-slate-100">
        <button onClick={copy} className="absolute right-2 top-2 rounded bg-slate-700 px-2 py-0.5 text-xs text-white hover:bg-slate-600">
          {copied ? "Copied" : "Copy"}
        </button>
        <pre tabIndex={0} aria-label="Code" className="scroll-thin overflow-x-auto rounded-b-lg bg-slate-900 p-3 pr-16 text-xs leading-relaxed text-slate-100">
          <code>{code}</code>
        </pre>
      </div>
    </details>
  );
}
