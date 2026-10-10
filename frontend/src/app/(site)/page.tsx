import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import landing from "@/assets/screenshots/landing.webp";
import BeforeAfter from "@/components/site/BeforeAfter";
import Guarantee from "@/components/site/Guarantee";
import JsonLd from "@/components/site/JsonLd";
import Tooltip from "@/components/site/Tooltip";
import { formatDate, posts } from "@/lib/blog";
import { examples } from "@/lib/examples";
import { features } from "@/lib/features";
import { absoluteUrl, site } from "@/lib/site";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

const software = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: site.name,
  url: absoluteUrl("/"),
  description: site.description,
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web browser",
  publisher: { "@id": absoluteUrl("/#organization") },
  featureList: features.map((f) => f.name),
};

export default function HomePage() {
  return (
    <>
      <JsonLd data={software} />
      <section className="relative overflow-hidden border-b border-slate-200 bg-surface">
        <div aria-hidden="true" className="pointer-events-none absolute -right-40 -top-40 h-[32rem] w-[32rem] rounded-full bg-brand-100/60 blur-3xl" />
        <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 sm:px-6 lg:grid-cols-[1fr_1.15fr] lg:py-24">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700 ring-1 ring-brand-100">
              AI data analyst for CSV files and databases
            </p>
            <h1 className="mt-5 text-4xl font-semibold leading-tight tracking-tight text-slate-900 sm:text-5xl">
              Ask your data a question. Get an answer you can check.
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-slate-600">
              DataPilot plans the analysis with AI, then computes every number with SQL or Python on your real data. The code is shown under each answer, so nothing has to be taken on trust.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/login?mode=register" className="rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-700">
                Get started
              </Link>
              <Link href="/examples" className="rounded-lg px-5 py-2.5 text-sm font-semibold text-slate-800 ring-1 ring-slate-300 hover:bg-slate-100">
                See before and after
              </Link>
            </div>
            <ul className="mt-8 grid gap-2 text-sm text-slate-600 sm:grid-cols-2">
              <li className="flex gap-2"><Check />Answers grounded in executed queries</li>
              <li className="flex gap-2"><Check />Charts, anomalies and quality reports</li>
              <li className="flex gap-2"><Check />Joins across files without double counting</li>
              <li className="flex gap-2"><Check />Private workspaces, teams and SSO</li>
            </ul>
          </div>
          <Image
            src={landing}
            alt="DataPilot analyst view with datasets, inferred relationships and suggested questions"
            priority
            placeholder="blur"
            sizes="(min-width: 1024px) 620px, 100vw"
            className="h-auto w-full rounded-2xl border border-slate-200 shadow-float"
          />
        </div>
      </section>

      <section aria-labelledby="how-title" className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <h2 id="how-title" className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
          The model plans. The database computes.
        </h2>
        <p className="mt-3 max-w-2xl leading-relaxed text-slate-600">
          General purpose chatbots generate numbers that look right. DataPilot splits the job so that every figure has a source you can inspect.
        </p>
        <ol className="mt-10 grid gap-5 md:grid-cols-3">
          <Step n={1} title="Understand">
            The language model reads your question and the{" "}
            <Tooltip label="schema" title="Schema">
              Table names, row counts, column types and summary statistics, plus the relationships between your datasets. It is enough to plan a query without guessing column names.
            </Tooltip>{" "}
            and decides what has to be computed.
          </Step>
          <Step n={2} title="Compute">
            DuckDB runs validated, read-only SQL, or a{" "}
            <Tooltip label="sandboxed" title="Sandboxed Python">
              Python runs in a separate process with memory, CPU and time limits, an empty environment and no permission to write files. It reads a Parquet export of your tables, not the original uploads.
            </Tooltip>{" "}
            Python process runs the statistics, on every row of your data.
          </Step>
          <Step n={3} title="Explain and verify">
            The answer quotes the tool results, the code is shown, and a{" "}
            <Tooltip label="grounding check" title="Grounding check">
              After each answer, numbers in the text are compared with the numbers returned by tools. Any figure with no source is flagged so you know to check it.
            </Tooltip>{" "}
            flags any figure that no query produced.
          </Step>
        </ol>
        <div className="mt-10">
          <Guarantee />
        </div>
      </section>

      <section aria-labelledby="features-title" className="border-y border-slate-200 bg-surface">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <h2 id="features-title" className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
              Everything an analyst does, with the work shown
            </h2>
            <Link href="/features" className="text-sm font-semibold text-brand-700 hover:underline">
              All features
            </Link>
          </div>
          <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {features.map((f) => (
              <li key={f.slug}>
                <Link href={`/features/${f.slug}`} className="group block h-full rounded-xl border border-slate-200 p-5 transition hover:border-brand-500 hover:shadow-card">
                  <h3 className="font-semibold text-slate-900 group-hover:text-brand-700">{f.name}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">{f.summary}</p>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section aria-labelledby="examples-title" className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h2 id="examples-title" className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
            Before and after
          </h2>
          <Link href="/examples" className="text-sm font-semibold text-brand-700 hover:underline">
            See all examples
          </Link>
        </div>
        <p className="mt-3 max-w-2xl leading-relaxed text-slate-600">Real sample files on the left. What DataPilot produced from them on the right.</p>
        <div className="mt-8">
          <BeforeAfter example={examples[0]} />
        </div>
      </section>

      <section aria-labelledby="blog-title" className="border-t border-slate-200 bg-surface">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <h2 id="blog-title" className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
              From the blog
            </h2>
            <Link href="/blog" className="text-sm font-semibold text-brand-700 hover:underline">
              All posts
            </Link>
          </div>
          <ul className="mt-8 grid gap-5 md:grid-cols-3">
            {posts.slice(0, 3).map((post) => (
              <li key={post.slug}>
                <Link href={`/blog/${post.slug}`} className="group block h-full rounded-xl border border-slate-200 p-5 transition hover:border-brand-500 hover:shadow-card">
                  <p className="text-xs text-slate-500">
                    <time dateTime={post.published}>{formatDate(post.published)}</time> · {post.minutes} min read
                  </p>
                  <h3 className="mt-2 font-semibold leading-snug text-slate-900 group-hover:text-brand-700">{post.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">{post.description}</p>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="bg-gradient-to-br from-brand-700 via-brand-600 to-sky-600">
        <div className="mx-auto flex max-w-6xl flex-col items-start gap-6 px-4 py-14 sm:px-6 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-2xl font-semibold text-white sm:text-3xl">Bring a CSV. Leave with answers you can defend.</h2>
            <p className="mt-2 text-white/85">Sample datasets are built in, so you can try it before uploading anything.</p>
          </div>
          <Link href="/login?mode=register" className="rounded-lg bg-white px-5 py-2.5 text-sm font-semibold text-brand-700 shadow-sm hover:bg-brand-50">
            Get started
          </Link>
        </div>
      </section>
    </>
  );
}

function Check() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4.5 10.5l3.5 3.5 7.5-8" />
    </svg>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <li className="rounded-xl border border-slate-200 bg-surface p-6 shadow-card">
      <span aria-hidden="true" className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-600 text-sm font-semibold text-white">
        {n}
      </span>
      <h3 className="mt-4 font-semibold text-slate-900">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">{children}</p>
    </li>
  );
}
