import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import PageIntro from "@/components/site/PageIntro";
import { features } from "@/lib/features";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Features",
  description: "Natural language analysis, charts, anomaly detection, data quality reports, multi-file joins, connectors, scheduled queries and team sharing.",
  path: "/features",
});

export default function FeaturesPage() {
  return (
    <>
      <PageIntro
        crumbs={[{ name: "Features", href: "/features" }]}
        title="Features"
        lead="Each capability follows the same rule: the model plans, deterministic tools compute, and you can see the work."
      />
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <ul className="grid gap-6 md:grid-cols-2">
          {features.map((f) => (
            <li key={f.slug}>
              <Link href={`/features/${f.slug}`} className="group flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-surface shadow-card transition hover:border-brand-500">
                <Image src={f.image} alt="" placeholder="blur" sizes="(min-width: 768px) 560px, 100vw" className="aspect-[16/9] h-auto w-full border-b border-slate-200 object-cover object-left-top" />
                <div className="flex flex-1 flex-col p-6">
                  <h2 className="text-lg font-semibold text-slate-900 group-hover:text-brand-700">{f.name}</h2>
                  <p className="mt-2 flex-1 text-sm leading-relaxed text-slate-600">{f.summary}</p>
                  <span className="mt-4 text-sm font-semibold text-brand-700">Learn more</span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
