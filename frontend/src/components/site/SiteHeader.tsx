import Link from "next/link";
import { ArrowRight } from "./Icons";
import Logo from "./Logo";
import { smallPrimaryButton } from "./ui";

const nav = [
  { href: "/features", label: "Features" },
  { href: "/examples", label: "Examples" },
  { href: "/blog", label: "Blog" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
];

export default function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-surface/95 backdrop-blur">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:rounded-lg focus:bg-brand-600 focus:px-3 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to content
      </a>
      <div className="mx-auto flex h-[72px] max-w-[1200px] items-center justify-between gap-4 px-4 sm:px-6">
        <Logo />
        <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
          {nav.map((item) => (
            <Link key={item.href} href={item.href} className="rounded px-3 py-2 text-sm font-medium text-slate-700 hover:text-brand-600">
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Link href="/login" className="hidden rounded px-3 py-2 text-sm font-medium text-slate-900 hover:text-brand-600 sm:inline-block">
            Sign in
          </Link>
          <Link href="/login?mode=register" className={smallPrimaryButton}>
            Get started
            <ArrowRight />
          </Link>
          <details className="group relative md:hidden">
            <summary
              aria-label="Menu"
              className="flex h-9 w-9 cursor-pointer list-none items-center justify-center rounded text-slate-900 ring-1 ring-slate-200 [&::-webkit-details-marker]:hidden"
            >
              <svg aria-hidden="true" viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                <path d="M3 6h14M3 10h14M3 14h14" className="group-open:hidden" />
                <path d="M5 5l10 10M15 5L5 15" className="hidden group-open:block" />
              </svg>
            </summary>
            <nav aria-label="Mobile" className="absolute right-0 top-12 w-56 rounded-xl border border-slate-200 bg-surface p-2 shadow-float">
              {[...nav, { href: "/login", label: "Sign in" }].map((item) => (
                <Link key={item.href} href={item.href} className="block rounded px-3 py-2 text-sm font-medium text-slate-900 hover:bg-brand-50 hover:text-brand-700">
                  {item.label}
                </Link>
              ))}
            </nav>
          </details>
        </div>
      </div>
    </header>
  );
}
