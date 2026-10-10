import type { Metadata } from "next";
import Link from "next/link";
import Guarantee from "@/components/site/Guarantee";
import PageIntro from "@/components/site/PageIntro";
import { pageMetadata } from "@/lib/seo";
import { site } from "@/lib/site";

export const metadata: Metadata = pageMetadata({
  title: "About",
  description: "Why DataPilot exists, the principles behind it and how it is built.",
  path: "/about",
});

const principles = [
  {
    title: "Show the work",
    body: "An answer without its query is an opinion. Every DataPilot answer carries the SQL or Python that produced it, and figures that no tool returned are flagged.",
  },
  {
    title: "Use the right tool for each step",
    body: "Language models are excellent at understanding questions and planning. Databases are excellent at arithmetic. DataPilot never asks a model to do a database's job.",
  },
  {
    title: "Private by design",
    body: "Workspaces are isolated per user. API keys you bring are kept in server memory only and never written to disk. Connectors refuse private network addresses by default.",
  },
  {
    title: "Honest about uncertainty",
    body: "Data quality problems are reported up front, anomalies come with the method and bounds that flagged them, and malformed rows are counted rather than hidden.",
  },
];

const github = site.social.find((s) => s.name === "GitHub");

export default function AboutPage() {
  return (
    <>
      <PageIntro
        crumbs={[{ name: "About", href: "/about" }]}
        title="An AI analyst you can audit"
        lead="DataPilot started from a simple frustration: AI tools that answer data questions with confident numbers nobody can trace. We built the analyst we wanted to use, one that shows exactly how every figure was computed."
      />
      <div className="mx-auto max-w-6xl space-y-16 px-4 py-12 sm:px-6">
        <section aria-labelledby="principles-title">
          <h2 id="principles-title" className="text-2xl font-semibold tracking-tight text-slate-900">
            What we believe
          </h2>
          <ul className="mt-6 grid gap-5 md:grid-cols-2">
            {principles.map((p) => (
              <li key={p.title} className="rounded-xl border border-slate-200 bg-surface p-6">
                <h3 className="font-semibold text-slate-900">{p.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">{p.body}</p>
              </li>
            ))}
          </ul>
        </section>

        <Guarantee />

        <section aria-labelledby="built-title" className="grid gap-10 md:grid-cols-2">
          <div>
            <h2 id="built-title" className="text-2xl font-semibold tracking-tight text-slate-900">
              How it is built
            </h2>
            <p className="mt-4 leading-relaxed text-slate-600">
              DataPilot is a Next.js interface on top of a FastAPI service. Each workspace keeps its datasets in its own DuckDB file, so analyses survive restarts and large files spill to disk instead of exhausting memory. An agent loop sends the question and the dataset schema to the language model you choose, Gemini, OpenAI or Anthropic, and routes the model&apos;s tool calls to deterministic tools for SQL, sandboxed Python, charts, anomaly detection and quality checks.
            </p>
            <p className="mt-4 leading-relaxed text-slate-600">
              Structured logs, Prometheus metrics, rate limits and an evaluation suite of benchmark questions keep the system observable and its answers measurable.
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-surface p-6">
            <h2 className="text-lg font-semibold text-slate-900">Get in touch</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">Questions about DataPilot, team plans or security? We read every message.</p>
            <div className="mt-4 flex flex-wrap gap-3">
              <Link href="/contact" className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700">
                Contact us
              </Link>
              {github && (
                <a href={github.url} target="_blank" rel="noopener noreferrer" className="rounded-lg px-4 py-2 text-sm font-semibold text-slate-800 ring-1 ring-slate-300 hover:bg-slate-100">
                  Source on GitHub
                </a>
              )}
            </div>
          </div>
        </section>
      </div>
    </>
  );
}
