import type { Metadata } from "next";
import Link from "next/link";
import BeforeAfter from "@/components/site/BeforeAfter";
import PageIntro from "@/components/site/PageIntro";
import { examples } from "@/lib/examples";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Before and after examples",
  description: "Raw CSV files on one side, the quality reports, anomaly explanations, charts and joins DataPilot produced from them on the other.",
  path: "/examples",
});

export default function ExamplesPage() {
  return (
    <>
      <PageIntro
        crumbs={[{ name: "Examples", href: "/examples" }]}
        title="Before and after"
        lead="Every example uses the sample datasets that ship with DataPilot. The screenshots are real output from the app, only resized for the web."
      />
      <div className="mx-auto max-w-[1200px] space-y-8 px-4 py-12 sm:px-6">
        {examples.map((example) => (
          <BeforeAfter key={example.slug} example={example} headingLevel={2} />
        ))}
        <p className="text-center text-sm text-slate-600">
          Want to try it on the same files?{" "}
          <Link href="/login?mode=register" className="font-semibold text-brand-600 hover:underline">
            Create an account
          </Link>{" "}
          and choose Load samples.
        </p>
      </div>
    </>
  );
}
