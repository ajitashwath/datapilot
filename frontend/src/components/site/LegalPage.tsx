import Link from "next/link";
import { formatDate } from "@/lib/blog";
import { site } from "@/lib/site";
import PageIntro from "./PageIntro";

export interface LegalSection {
  id: string;
  title: string;
  body: React.ReactNode;
}

interface LegalPageProps {
  title: string;
  path: string;
  lead: string;
  effective: string;
  sections: LegalSection[];
}

export default function LegalPage({ title, path, lead, effective, sections }: LegalPageProps) {
  return (
    <>
      <PageIntro crumbs={[{ name: title, href: path }]} title={title} lead={lead}>
        <p className="mt-4 text-sm text-slate-500">
          Effective <time dateTime={effective}>{formatDate(effective)}</time>
        </p>
      </PageIntro>
      <div className="mx-auto grid max-w-[1200px] gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[220px_1fr]">
        <nav aria-label="On this page" className="hidden lg:block">
          <ol className="sticky top-24 space-y-2 text-sm">
            {sections.map((s, i) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className="text-slate-600 hover:text-brand-600 hover:underline">
                  {i + 1}. {s.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>
        <div className="max-w-3xl space-y-10 text-slate-700 [&_a]:font-medium [&_a]:text-brand-600 [&_a]:underline [&_li]:mt-1.5 [&_p]:mt-3 [&_p]:leading-relaxed [&_ul]:mt-3 [&_ul]:list-disc [&_ul]:pl-6">
          {sections.map((s, i) => (
            <section key={s.id} id={s.id} aria-labelledby={`${s.id}-title`} className="scroll-mt-24">
              <h2 id={`${s.id}-title`} className="text-xl font-semibold text-slate-900">
                {i + 1}. {s.title}
              </h2>
              {s.body}
            </section>
          ))}
          <p className="border-t border-slate-200 pt-6 text-sm text-slate-500">
            Questions about this page?{" "}
            {site.email ? <a href={`mailto:${site.email}`}>{site.email}</a> : <Link href="/contact">Contact us</Link>}
          </p>
        </div>
      </div>
    </>
  );
}
