import { FeatureIcon } from "./Icons";

export const GUARANTEE_TITLE = "The verified numbers guarantee";

export const GUARANTEE_TEXT =
  "Every number DataPilot reports is computed by SQL or Python that ran on your data, and that code is shown with the answer. If an answer contains a figure that no query produced, DataPilot flags it before you rely on it.";

export default function Guarantee() {
  return (
    <aside aria-labelledby="guarantee-title" className="flex flex-col gap-4 rounded-xl border border-slate-200 p-6 sm:flex-row sm:items-start sm:p-8">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-600">
        <FeatureIcon name="verify" />
      </span>
      <div>
        <h2 id="guarantee-title" className="text-lg font-semibold text-slate-900">
          {GUARANTEE_TITLE}
        </h2>
        <p className="mt-1 max-w-3xl leading-relaxed text-slate-600">{GUARANTEE_TEXT}</p>
      </div>
    </aside>
  );
}
