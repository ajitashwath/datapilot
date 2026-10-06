export function formatNumber(value: number, maxDigits = 2): string {
  if (!Number.isFinite(value)) return String(value);
  return value.toLocaleString("en-US", { maximumFractionDigits: maxDigits });
}

export function compactNumber(value: number): string {
  return value.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 1 });
}

export function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : formatNumber(value, 4);
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

export function scoreColor(score: number): string {
  if (score >= 90) return "text-emerald-700 bg-emerald-50 ring-emerald-200";
  if (score >= 70) return "text-amber-700 bg-amber-50 ring-amber-200";
  return "text-rose-700 bg-rose-50 ring-rose-200";
}
