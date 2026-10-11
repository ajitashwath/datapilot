import type { Metadata } from "next";
import ContactDetails, { hasContactDetails } from "@/components/site/ContactDetails";
import ContactForm from "@/components/site/ContactForm";
import PageIntro from "@/components/site/PageIntro";
import { pageMetadata } from "@/lib/seo";
import { site } from "@/lib/site";

export const metadata: Metadata = pageMetadata({
  title: "Contact",
  description: "Questions about DataPilot, teams, security or privacy. Send us a message and we will reply by email.",
  path: "/contact",
});

export default function ContactPage() {
  return (
    <>
      <PageIntro
        crumbs={[{ name: "Contact", href: "/contact" }]}
        title="Contact us"
        lead="Questions about DataPilot, team rollouts, security or your data? Send a message and we will reply by email."
      />
      <div className="mx-auto grid max-w-[1200px] gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[1.4fr_1fr] lg:items-start">
        <section aria-labelledby="form-title" className="rounded-xl border border-slate-200 p-6 sm:p-8">
          <h2 id="form-title" className="text-lg font-semibold text-slate-900">
            Send a message
          </h2>
          <ContactForm fallbackEmail={site.email} />
        </section>
        <aside aria-label="Contact details" className="space-y-6">
          {hasContactDetails() && (
            <section className="rounded-xl border border-slate-200 p-6">
              <h2 className="mb-4 text-lg font-semibold text-slate-900">
                Other ways to reach us
              </h2>
              <ContactDetails />
            </section>
          )}
          <section className="rounded-xl border border-slate-200 p-6">
            <h2 className="text-lg font-semibold text-slate-900">Security reports</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              Found a vulnerability? Send it with the topic &quot;Security report&quot;, or by email, and include steps to reproduce. Please give us a reasonable time to fix the issue before disclosing it publicly.
            </p>
          </section>
        </aside>
      </div>
    </>
  );
}
