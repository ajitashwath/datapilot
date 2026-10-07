"use client";

import { useEffect, useRef } from "react";

export default function Modal({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
    return () => dialog?.close();
  }, []);

  return (
    <dialog
      ref={ref}
      aria-label={title}
      onClose={() => {
        if (!ref.current?.open) onClose();
      }}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
      className={`m-auto w-[calc(100%-2rem)] rounded-2xl border border-slate-200 bg-surface p-0 text-slate-800 shadow-float backdrop:bg-black/50 ${wide ? "max-w-2xl" : "max-w-md"}`}
    >
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
        <h2 className="text-base font-semibold text-slate-900">{title}</h2>
        <button onClick={onClose} aria-label="Close dialog" className="rounded-md px-2 py-1 text-slate-500 hover:bg-slate-100">
          &#10005;
        </button>
      </div>
      <div className="max-h-[75vh] overflow-y-auto px-5 py-4">{children}</div>
    </dialog>
  );
}
