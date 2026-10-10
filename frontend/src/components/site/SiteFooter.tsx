import Link from "next/link";
import { features } from "@/lib/features";
import { site } from "@/lib/site";
import ContactDetails, { hasContactDetails } from "./ContactDetails";
import CookieSettingsButton from "./CookieSettingsButton";
import Logo from "./Logo";
import SocialIcon from "./SocialIcon";

const linkClass = "text-sm text-slate-600 hover:text-brand-700 hover:underline";

export default function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-slate-200 bg-surface">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div>
          <Logo />
          <p className="mt-3 max-w-xs text-sm leading-relaxed text-slate-600">{site.tagline}. Answers computed on your real data, with the code shown.</p>
          {hasContactDetails() && (
            <div className="mt-5">
              <ContactDetails compact />
            </div>
          )}
          {site.social.length > 0 && (
            <ul className="mt-5 flex gap-2" aria-label="Social media">
              {site.social.map((link) => (
                <li key={link.name}>
                  <a
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer me"
                    aria-label={`DataPilot on ${link.name} (opens in a new tab)`}
                    className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 ring-1 ring-slate-200 hover:bg-slate-100 hover:text-slate-900"
                  >
                    <SocialIcon name={link.name} />
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
        <nav aria-labelledby="footer-product">
          <h2 id="footer-product" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Product
          </h2>
          <ul className="mt-3 space-y-2">
            {features.map((f) => (
              <li key={f.slug}>
                <Link href={`/features/${f.slug}`} className={linkClass}>
                  {f.name}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <nav aria-labelledby="footer-resources">
          <h2 id="footer-resources" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Resources
          </h2>
          <ul className="mt-3 space-y-2">
            <li><Link href="/examples" className={linkClass}>Before and after examples</Link></li>
            <li><Link href="/blog" className={linkClass}>Blog</Link></li>
            <li><Link href="/login" className={linkClass}>Sign in</Link></li>
            <li><Link href="/login?mode=register" className={linkClass}>Create an account</Link></li>
          </ul>
        </nav>
        <nav aria-labelledby="footer-company">
          <h2 id="footer-company" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Company
          </h2>
          <ul className="mt-3 space-y-2">
            <li><Link href="/about" className={linkClass}>About</Link></li>
            <li><Link href="/contact" className={linkClass}>Contact</Link></li>
            <li><Link href="/terms" className={linkClass}>Terms of service</Link></li>
            <li><Link href="/privacy" className={linkClass}>Privacy policy</Link></li>
            <li><CookieSettingsButton className={linkClass} /></li>
          </ul>
        </nav>
      </div>
      <div className="border-t border-slate-200">
        <p className="mx-auto max-w-6xl px-4 py-5 text-xs text-slate-500 sm:px-6">
          &copy; {year} {site.legalName}. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
