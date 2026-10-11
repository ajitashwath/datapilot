import Link from "next/link";
import BrandMark from "@/components/BrandMark";

export default function Logo({ className = "" }: { className?: string }) {
  return (
    <Link href="/" className={`flex items-center gap-2.5 rounded-lg ${className}`} aria-label="DataPilot home">
      <BrandMark className="h-7 w-auto" />
      <span className="text-base font-semibold text-slate-900">DataPilot</span>
    </Link>
  );
}
