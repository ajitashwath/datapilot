export interface FieldControl {
  id: string;
  "aria-invalid": boolean;
  "aria-describedby"?: string;
  className: string;
}

interface FormFieldProps {
  id: string;
  label: string;
  error?: string;
  hint?: React.ReactNode;
  optional?: boolean;
  className?: string;
  children: (control: FieldControl) => React.ReactNode;
}

export const controlClass = (invalid: boolean) =>
  `mt-1 w-full rounded-lg border bg-surface px-3 py-2 text-sm text-slate-900 outline-none transition focus:ring-2 ${
    invalid ? "border-rose-500 focus:border-rose-500 focus:ring-rose-200" : "border-slate-300 focus:border-brand-500 focus:ring-brand-100"
  }`;

export default function FormField({ id, label, error, hint, optional, className = "", children }: FormFieldProps) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={className}>
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
        {optional && <span className="font-normal text-slate-500"> (optional)</span>}
      </label>
      {children({ id, "aria-invalid": Boolean(error), "aria-describedby": describedBy, className: controlClass(Boolean(error)) })}
      {error && (
        <p id={errorId} className="mt-1 flex items-start gap-1 text-sm text-rose-700">
          <svg aria-hidden="true" viewBox="0 0 20 20" className="mt-0.5 h-4 w-4 shrink-0" fill="currentColor">
            <path d="M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16zm-.9 4h1.8v5.2H9.1zm0 6.6h1.8v1.8H9.1z" />
          </svg>
          <span>{error}</span>
        </p>
      )}
      {hint && (
        <div id={hintId} className="mt-1 text-xs text-slate-500">
          {hint}
        </div>
      )}
    </div>
  );
}
