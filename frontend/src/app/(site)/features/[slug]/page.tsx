import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import Guarantee from "@/components/site/Guarantee";
import PageIntro from "@/components/site/PageIntro";
import { featureBySlug, features } from "@/lib/features";
import { pageMetadata } from "@/lib/seo";

type Props = { params: Promise<{ slug: string }> };

export const dynamicParams = false;

export function generateStaticParams() {
  return features.map((f) => ({ slug: f.slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const feature = featureBySlug((await params).slug);
  if (!feature) return {};
  return pageMetadata({ title: feature.name, description: feature.summary, path: `/features/${feature.slug}` });
}

export default async function FeaturePage({ params }: Props) {
  const feature = featureBySlug((await params).slug);
  if (!feature) notFound();
  const others = features.filter((f) => f.slug !== feature.slug).slice(0, 3);

  return (
    <>
      <PageIntro
        crumbs={[
          { name: "Features", href: "/features" },
          { name: feature.name, href: `/features/${feature.slug}` },
        ]}
        title={feature.headline}
        lead={feature.intro}
      >
        <div className="mt-8 flex flex-wrap gap-3">
          <Link href="/login?mode=register" className="rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-700">
            Get started
          </Link>
          <Link href="/contact" className="rounded-lg px-5 py-2.5 text-sm font-semibold text-slate-800 ring-1 ring-slate-300 hover:bg-slate-100">
            Talk to us
          </Link>
        </div>
      </PageIntro>

      <div className="mx-auto max-w-6xl space-y-16 px-4 py-12 sm:px-6">
        <Image
          src={feature.image}
          alt={feature.imageAlt}
          placeholder="blur"
          sizes="(min-width: 1152px) 1104px, 100vw"
          className="h-auto w-full rounded-2xl border border-slate-200 shadow-float"
        />

        <section aria-labelledby="points-title">
          <h2 id="points-title" className="text-2xl font-semibold tracking-tight text-slate-900">
            What you get
          </h2>
          <ul className="mt-6 grid gap-5 md:grid-cols-3">
            {feature.points.map((point) => (
              <li key={point.title} className="rounded-xl border border-slate-200 bg-surface p-6">
                <h3 className="font-semibold text-slate-900">{point.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">{point.body}</p>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="steps-title" className="grid gap-10 md:grid-cols-2">
          <div>
            <h2 id="steps-title" className="text-2xl font-semibold tracking-tight text-slate-900">
              How it works
            </h2>
            <ol className="mt-6 space-y-4">
              {feature.steps.map((step, i) => (
                <li key={step} className="flex gap-4">
                  <span aria-hidden="true" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-600 text-sm font-semibold text-white">
                    {i + 1}
                  </span>
                  <span className="pt-0.5 text-slate-700">{step}</span>
                </li>
              ))}
            </ol>
          </div>
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-slate-900">Questions</h2>
            <dl className="mt-6 space-y-5">
              {feature.faqs.map((faq) => (
                <div key={faq.q}>
                  <dt className="font-semibold text-slate-900">{faq.q}</dt>
                  <dd className="mt-1 text-sm leading-relaxed text-slate-600">{faq.a}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <Guarantee />

        <nav aria-labelledby="more-title">
          <h2 id="more-title" className="text-lg font-semibold text-slate-900">
            More features
          </h2>
          <ul className="mt-4 grid gap-4 md:grid-cols-3">
            {others.map((f) => (
              <li key={f.slug}>
                <Link href={`/features/${f.slug}`} className="group block h-full rounded-xl border border-slate-200 bg-surface p-5 hover:border-brand-500">
                  <span className="font-semibold text-slate-900 group-hover:text-brand-700">{f.name}</span>
                  <span className="mt-1 block text-sm text-slate-600">{f.summary}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </>
  );
}
