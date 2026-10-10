import type { Metadata } from "next";
import Link from "next/link";
import LegalPage, { type LegalSection } from "@/components/site/LegalPage";
import { GUARANTEE_TEXT, GUARANTEE_TITLE } from "@/components/site/Guarantee";
import { pageMetadata } from "@/lib/seo";
import { site } from "@/lib/site";

export const metadata: Metadata = pageMetadata({
  title: "Terms of service",
  description: "The terms that apply when you use DataPilot.",
  path: "/terms",
});

const sections: LegalSection[] = [
  {
    id: "agreement",
    title: "Agreement",
    body: (
      <p>
        These terms are an agreement between you and {site.legalName} (&quot;we&quot;, &quot;us&quot;) for the use of DataPilot (the &quot;service&quot;). By creating an account or using the service you accept them. If you use the service for an organisation, you confirm that you can accept these terms on its behalf.
      </p>
    ),
  },
  {
    id: "accounts",
    title: "Accounts",
    body: (
      <ul>
        <li>Give accurate information and keep your password and recovery codes safe.</li>
        <li>You are responsible for activity under your account. Tell us promptly if you suspect unauthorised access.</li>
        <li>Team admins control membership and roles in their teams and are responsible for who they invite.</li>
      </ul>
    ),
  },
  {
    id: "your-data",
    title: "Your data",
    body: (
      <>
        <p>
          You keep all rights to the data you upload, import or create. You give us permission to store and process it only to provide the service to you, including sending it to the language model provider configured for your workspace as described in our <Link href="/privacy">privacy policy</Link>.
        </p>
        <p>You confirm that you have the right to use the data you bring and that processing it with the service does not break any law or agreement.</p>
      </>
    ),
  },
  {
    id: "acceptable-use",
    title: "Acceptable use",
    body: (
      <>
        <p>You must not:</p>
        <ul>
          <li>break the law, or upload data you have no right to process;</li>
          <li>attempt to access other users&apos; workspaces, bypass rate limits or quotas, or probe the service for vulnerabilities without permission;</li>
          <li>use connectors to reach systems you are not authorised to access;</li>
          <li>disrupt the service or use it to send spam or malware;</li>
          <li>resell the service without our written agreement.</li>
        </ul>
        <p>Responsible security research reported through the <Link href="/contact">contact page</Link> is welcome.</p>
      </>
    ),
  },
  {
    id: "guarantee",
    title: GUARANTEE_TITLE,
    body: (
      <>
        <p>{GUARANTEE_TEXT}</p>
        <p>
          This commitment is about traceability: every figure can be checked against the query that produced it. The interpretation of a question, the choice of query and the conclusions you draw remain your responsibility, so review the code shown with important answers before relying on them.
        </p>
      </>
    ),
  },
  {
    id: "third-party",
    title: "Third party services",
    body: (
      <p>
        The service relies on language model providers, and optionally on your own API keys, Google Sheets, Postgres or other sources you connect. Their availability and terms are outside our control, and you are responsible for complying with the terms of any provider whose key or account you use.
      </p>
    ),
  },
  {
    id: "availability",
    title: "Availability and changes",
    body: (
      <p>
        We work to keep the service available and secure, but it is provided &quot;as is&quot; and may change, be interrupted or have limits such as file size, question quotas and schedule frequency. We may update features, and we will give reasonable notice before removing something material that you rely on.
      </p>
    ),
  },
  {
    id: "liability",
    title: "Liability",
    body: (
      <p>
        To the extent the law allows, we are not liable for indirect or consequential losses, lost profits or lost data, and our total liability for any claim is limited to the amount you paid us for the service in the twelve months before the claim. Nothing in these terms limits liability that cannot be limited by law.
      </p>
    ),
  },
  {
    id: "ending",
    title: "Ending the agreement",
    body: (
      <p>
        You can stop using the service and delete your workspaces at any time. We may suspend or close accounts that break these terms, with notice where reasonable. Sections that by their nature should survive, such as liability, continue after the agreement ends.
      </p>
    ),
  },
  {
    id: "law",
    title: "Governing law and changes",
    body: (
      <>
        <p>
          {site.jurisdiction
            ? `These terms are governed by the laws of ${site.jurisdiction}, and its courts have jurisdiction over disputes, unless mandatory consumer law where you live says otherwise.`
            : "These terms are governed by the laws of the place where the operator is established, unless mandatory consumer law where you live says otherwise."}
        </p>
        <p>We may update these terms. If a change is material, we will update the effective date and notify account holders before it applies.</p>
      </>
    ),
  },
];

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of service"
      path="/terms"
      lead="The rules for using DataPilot, written to be read."
      effective={site.updated}
      sections={sections}
    />
  );
}
