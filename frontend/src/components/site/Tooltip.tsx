"use client";

import { useEffect, useId, useState } from "react";

interface TooltipProps {
  label: string;
  title: string;
  children: React.ReactNode;
}

export default function Tooltip({ label, title, children }: TooltipProps) {
  const id = useId();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);

  return (
    <span className="relative inline-block" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        aria-describedby={id}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen(true)}
        className="cursor-help border-b border-dotted border-current font-medium text-inherit"
      >
        {label}
      </button>
      <span
        id={id}
        role="tooltip"
        className={`absolute bottom-full left-1/2 z-30 mb-2 w-72 max-w-[80vw] -translate-x-1/2 rounded-xl border border-slate-200 bg-surface p-3 text-left text-sm font-normal normal-case leading-relaxed tracking-normal text-slate-600 shadow-float transition ${open ? "visible translate-y-0 opacity-100" : "invisible translate-y-1 opacity-0"}`}
      >
        <span className="mb-1 block text-sm font-semibold text-slate-900">{title}</span>
        {children}
      </span>
    </span>
  );
}
