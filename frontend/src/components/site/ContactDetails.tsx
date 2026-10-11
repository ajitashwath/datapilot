import { describeDays, site, telHref } from "@/lib/site";

export function hasContactDetails() {
  return Boolean(site.email || site.phone || site.hours.length);
}

export default function ContactDetails({ compact = false }: { compact?: boolean }) {
  const label = compact ? "text-xs font-semibold uppercase tracking-wide text-slate-500" : "text-sm font-semibold text-slate-900";
  return (
    <dl className={compact ? "space-y-3 text-sm" : "space-y-5"}>
      {site.email && (
        <div>
          <dt className={label}>Email</dt>
          <dd className="mt-0.5">
            <a href={`mailto:${site.email}`} className="font-medium text-brand-600 hover:underline">
              {site.email}
            </a>
          </dd>
        </div>
      )}
      {site.phone && (
        <div>
          <dt className={label}>Phone</dt>
          <dd className="mt-0.5">
            <a href={telHref(site.phone)} className="inline-flex items-center gap-1.5 font-medium text-brand-600 hover:underline">
              <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M6.5 3h-2A1.5 1.5 0 0 0 3 4.6C3.3 11 9 16.7 15.4 17a1.5 1.5 0 0 0 1.6-1.5v-2l-3.5-1.5-1.7 1.7a9 9 0 0 1-4.5-4.5l1.7-1.7z" />
              </svg>
              <span>{site.phone}</span>
              <span className="sr-only">(tap to call)</span>
            </a>
          </dd>
        </div>
      )}
      {site.hours.length > 0 && (
        <div>
          <dt className={label}>Support hours</dt>
          <dd className="mt-0.5 text-slate-600">
            <ul>
              {site.hours.map((rule) => (
                <li key={rule.days.join()}>
                  {describeDays(rule.days)}, <time>{rule.opens}</time> to <time>{rule.closes}</time>
                </li>
              ))}
            </ul>
            <span className="text-xs text-slate-500">Times are {site.timezone}.</span>
          </dd>
        </div>
      )}
    </dl>
  );
}
