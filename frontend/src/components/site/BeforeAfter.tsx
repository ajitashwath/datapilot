import Image from "next/image";
import Link from "next/link";
import type { Example } from "@/lib/examples";

export default function BeforeAfter({ example, headingLevel = 3 }: { example: Example; headingLevel?: 2 | 3 }) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <article className="rounded-2xl border border-slate-200 bg-surface p-5 shadow-card sm:p-6">
      <Heading className="text-lg font-semibold text-slate-900">{example.title}</Heading>
      {example.question && (
        <p className="mt-2 text-sm text-slate-600">
          Question asked: <q className="font-medium text-slate-800">{example.question}</q>
        </p>
      )}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <figure className="flex min-w-0 flex-col">
          <figcaption className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <span className="rounded-full bg-slate-200 px-2 py-0.5 text-slate-700">Before</span>
            {example.before.label}
          </figcaption>
          <pre className="scroll-thin flex-1 overflow-x-auto rounded-xl bg-code p-4 text-[11px] leading-relaxed text-code-fg" tabIndex={0}>
            <code>{example.before.text}</code>
          </pre>
        </figure>
        <figure className="flex min-w-0 flex-col">
          <figcaption className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <span className="rounded-full bg-brand-100 px-2 py-0.5 text-brand-700">After</span>
            {example.after.label}
          </figcaption>
          <Image
            src={example.after.image}
            alt={example.after.alt}
            placeholder="blur"
            sizes="(min-width: 1024px) 540px, 100vw"
            className="h-auto w-full rounded-xl border border-slate-200"
          />
        </figure>
      </div>
      <p className="mt-4 text-sm leading-relaxed text-slate-600">
        <span className="font-semibold text-slate-800">Result: </span>
        {example.outcome}{" "}
        <Link href={`/features/${example.feature}`} className="font-medium text-brand-700 hover:underline">
          How it works
        </Link>
      </p>
    </article>
  );
}
