import Link from "next/link";

export default function Logo({ className = "" }: { className?: string }) {
  return (
    <Link href="/" className={`flex items-center gap-2.5 rounded-lg ${className}`} aria-label="DataPilot home">
      <span aria-hidden="true" className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-sky-500 text-xs font-bold text-white">
        DP
      </span>
      <span className="text-base font-semibold text-slate-900">DataPilot</span>
    </Link>
  );
}
