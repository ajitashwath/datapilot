import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import landing from "@/assets/screenshots/landing.webp";
import BeforeAfter from "@/components/site/BeforeAfter";
import Faq from "@/components/site/Faq";
import Guarantee from "@/components/site/Guarantee";
import { ArrowRight, IconBubble, Sparkle } from "@/components/site/Icons";
import JsonLd from "@/components/site/JsonLd";
import Rays from "@/components/site/Rays";
import SectionHeading from "@/components/site/SectionHeading";
import Tooltip from "@/components/site/Tooltip";
import { container, ghostButton, pillBadge, primaryButton, sectionGap } from "@/components/site/ui";
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

const worksWith = ["Gemini", "OpenAI", "Anthropic", "CSV", "Google Sheets", "SQLite", "Postgres"];

export default function HomePage() {
  return (
    <>
      <JsonLd data={software} />

      <section className="relative overflow-hidden">
        <Rays />
        <div className={`relative ${container} flex flex-col items-center pb-20 pt-16 text-center sm:pt-24`}>
          <p className={pillBadge}>
            <Sparkle className="h-4 w-4 text-brand-500" />
            The AI data analyst that shows its work
          </p>
          <h1 className="mt-8 max-w-5xl text-[2.5rem] font-semibold leading-[1.05] tracking-tight sm:text-[3.5rem] lg:text-[4.5rem] lg:leading-none">
            <span className="block text-brand-500">Ask your data a question.</span>
            <span className="block text-slate-900">Get an answer you can check.</span>
          </h1>
          <p className="mt-6 max-w-[640px] text-lg leading-relaxed text-slate-700">
            DataPilot plans the analysis with AI, then computes every number with SQL or Python on your real data. The code is shown under each answer, so nothing has to be taken on trust.
          </p>
          <div className="mt-10 flex flex-wrap justify-center gap-4">
            <Link href="/login?mode=register" className={primaryButton}>
              Get started
              <ArrowRight />
            </Link>
            <Link href="/examples" className={ghostButton}>
              <Sparkle />
              See before and after
            </Link>
          </div>
          <div className="mt-10">
            <p className="text-sm text-slate-500">Works with</p>
            <ul className="mt-3 flex max-w-xl flex-wrap justify-center gap-x-5 gap-y-2 text-sm font-medium text-slate-700">
              {worksWith.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          </div>
        </div>
        <div className={`relative ${container} pb-20 sm:pb-28`}>
          <Image
            src={landing}
            alt="DataPilot analyst view with datasets, inferred relationships and suggested questions"
            priority
            placeholder="blur"
            sizes="(min-width: 1200px) 1152px, 100vw"
            className="h-auto w-full rounded-xl border border-slate-200 shadow-card"
          />
        </div>
      </section>

      <section aria-labelledby="how-title" className={`border-t border-slate-200 ${sectionGap}`}>
        <div className={container}>
          <SectionHeading id="how-title" first="The model plans." second="The database computes." lead="General purpose chatbots generate numbers that look right. DataPilot splits the job so that every figure has a source you can inspect." />
          <ol className="mt-16 grid gap-10 md:grid-cols-3 md:gap-8">
            <Step icon="understand" title="Understand">
              The language model reads your question and the{" "}
              <Tooltip label="schema" title="Schema">
                Table names, row counts, column types and summary statistics, plus the relationships between your datasets. It is enough to plan a query without guessing column names.
              </Tooltip>{" "}
              and decides what has to be computed.
            </Step>
            <Step icon="compute" title="Compute">
              DuckDB runs validated, read-only SQL, or a{" "}
              <Tooltip label="sandboxed" title="Sandboxed Python">
                Python runs in a separate process with memory, CPU and time limits, an empty environment and no permission to write files. It reads a Parquet export of your tables, not the original uploads.
              </Tooltip>{" "}
              Python process runs the statistics, on every row of your data.
            </Step>
            <Step icon="verify" title="Explain and verify">
              The answer quotes the tool results, the code is shown, and a{" "}
              <Tooltip label="grounding check" title="Grounding check">
                After each answer, numbers in the text are compared with the numbers returned by tools. Any figure with no source is flagged so you know to check it.
              </Tooltip>{" "}
              flags any figure that no query produced.
            </Step>
          </ol>
          <div className="mt-16">
            <Guarantee />
          </div>
        </div>
      </section>

      <section aria-labelledby="features-title" className={`border-t border-slate-200 ${sectionGap}`}>
        <div className={container}>
          <SectionHeading id="features-title" first="Everything an analyst does," second="with the work shown." />
          <ul className="mt-16 grid gap-x-8 gap-y-12 sm:grid-cols-2 lg:grid-cols-4">
            {features.map((f) => (
              <li key={f.slug}>
                <Link href={`/features/${f.slug}`} className="group block rounded-xl">
                  <IconBubble name={f.slug} />
                  <h3 className="mt-4 text-lg font-medium text-brand-600 group-hover:underline">{f.name}</h3>
                  <p className="mt-2 leading-relaxed text-slate-700">{f.summary}</p>
                </Link>
              </li>
            ))}
          </ul>
          <div className="mt-14 text-center">
            <Link href="/features" className="inline-flex items-center gap-2 font-medium text-brand-600 hover:underline">
              Explore all features
              <ArrowRight />
            </Link>
          </div>
        </div>
      </section>

      <section aria-labelledby="examples-title" className={`border-t border-slate-200 ${sectionGap}`}>
        <div className={container}>
          <SectionHeading id="examples-title" first="Before DataPilot," second="and after." lead="Real sample files on the left. What DataPilot produced from them on the right." />
          <div className="mt-16">
            <BeforeAfter example={examples[0]} />
          </div>
          <div className="mt-10 text-center">
            <Link href="/examples" className="inline-flex items-center gap-2 font-medium text-brand-600 hover:underline">
              See all examples
              <ArrowRight />
            </Link>
          </div>
        </div>
      </section>

      <section aria-labelledby="faq-title" className={`relative overflow-hidden border-t border-slate-200 ${sectionGap}`}>
        <Rays className="opacity-60" />
        <div className={`relative ${container} max-w-[880px]`}>
          <SectionHeading id="faq-title" first="Questions," second="answered." />
          <div className="mt-14">
            <Faq />
          </div>
        </div>
      </section>

      <section aria-labelledby="blog-title" className={`border-t border-slate-200 ${sectionGap}`}>
        <div className={container}>
          <SectionHeading id="blog-title" first="From the" second="blog." />
          <ul className="mt-16 grid gap-8 md:grid-cols-3">
            {posts.slice(0, 3).map((post) => (
              <li key={post.slug}>
                <Link href={`/blog/${post.slug}`} className="group block h-full rounded-xl border border-slate-200 p-8 transition hover:border-brand-500">
                  <p className="text-sm text-slate-500">
                    <time dateTime={post.published}>{formatDate(post.published)}</time> · {post.minutes} min read
                  </p>
                  <h3 className="mt-3 text-xl font-semibold leading-snug text-slate-900 group-hover:text-brand-600">{post.title}</h3>
                  <p className="mt-3 leading-relaxed text-slate-600">{post.description}</p>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section aria-labelledby="cta-title" className="relative overflow-hidden border-t border-slate-200">
        <Rays />
        <div className={`relative ${container} flex flex-col items-center py-28 text-center`}>
          <h2 id="cta-title" className="max-w-3xl text-[2.25rem] font-semibold leading-[1.11] tracking-tight sm:text-[3rem]">
            <span className="block text-slate-900">Bring a CSV.</span>
            <span className="block text-brand-500">Leave with answers you can defend.</span>
          </h2>
          <p className="mt-5 max-w-xl text-lg text-slate-700">Sample datasets are built in, so you can try it before uploading anything.</p>
          <div className="mt-10 flex flex-wrap justify-center gap-4">
            <Link href="/login?mode=register" className={primaryButton}>
              Get started
              <ArrowRight />
            </Link>
            <Link href="/contact" className={ghostButton}>
              Talk to us
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}

function Step({ icon, title, children }: { icon: string; title: string; children: React.ReactNode }) {
  return (
    <li>
      <IconBubble name={icon} />
      <h3 className="mt-4 text-lg font-medium text-brand-600">{title}</h3>
      <p className="mt-2 leading-relaxed text-slate-700">{children}</p>
    </li>
  );
}
