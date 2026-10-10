import JsonLd from "@/components/site/JsonLd";
import SiteFooter from "@/components/site/SiteFooter";
import SiteHeader from "@/components/site/SiteHeader";
import { absoluteUrl, site } from "@/lib/site";

const DAY_URL = "https://schema.org/";

function organization() {
  const contactPoint =
    site.email || site.phone
      ? [
          {
            "@type": "ContactPoint",
            contactType: "customer support",
            ...(site.email ? { email: site.email } : {}),
            ...(site.phone ? { telephone: site.phone } : {}),
            ...(site.hours.length > 0 && {
              hoursAvailable: site.hours.map((rule) => ({
                "@type": "OpeningHoursSpecification",
                dayOfWeek: rule.days.map((day) => DAY_URL + day),
                opens: rule.opens,
                closes: rule.closes,
              })),
            }),
          },
        ]
      : undefined;
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    "@id": absoluteUrl("/#organization"),
    name: site.legalName,
    url: absoluteUrl("/"),
    logo: absoluteUrl("/icon.png"),
    ...(site.email ? { email: site.email } : {}),
    ...(site.social.length > 0 ? { sameAs: site.social.map((s) => s.url) } : {}),
    ...(contactPoint ? { contactPoint } : {}),
  };
}

const website = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  "@id": absoluteUrl("/#website"),
  name: site.name,
  url: absoluteUrl("/"),
  publisher: { "@id": absoluteUrl("/#organization") },
};

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <JsonLd data={[organization(), website]} />
      <SiteHeader />
      <main id="content" className="flex-1">
        {children}
      </main>
      <SiteFooter />
    </div>
  );
}
