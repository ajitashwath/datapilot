export const GUARANTEE_TITLE = "The verified numbers guarantee";

export const GUARANTEE_TEXT =
  "Every number DataPilot reports is computed by SQL or Python that ran on your data, and that code is shown with the answer. If an answer contains a figure that no query produced, DataPilot flags it before you rely on it.";

export default function Guarantee({ tone = "light" }: { tone?: "light" | "brand" }) {
  const brand = tone === "brand";
  return (
    <aside
      aria-labelledby="guarantee-title"
      className={`flex gap-4 rounded-2xl p-5 ${brand ? "bg-white/10 text-white ring-1 ring-white/20" : "border border-brand-100 bg-brand-50 text-slate-700"}`}
    >
      <svg aria-hidden="true" viewBox="0 0 24 24" className={`h-8 w-8 shrink-0 ${brand ? "text-white" : "text-brand-600"}`} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3l7 3v5c0 4.4-3 8.3-7 9.5-4-1.2-7-5.1-7-9.5V6z" />
        <path d="M8.8 12.2l2.2 2.2 4.4-4.6" />
      </svg>
      <div>
        <h2 id="guarantee-title" className={`text-base font-semibold ${brand ? "text-white" : "text-slate-900"}`}>
          {GUARANTEE_TITLE}
        </h2>
        <p className={`mt-1 text-sm leading-relaxed ${brand ? "text-white/85" : "text-slate-600"}`}>{GUARANTEE_TEXT}</p>
      </div>
    </aside>
  );
}
