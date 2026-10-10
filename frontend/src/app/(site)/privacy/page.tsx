import type { Metadata } from "next";
import Link from "next/link";
import LegalPage, { type LegalSection } from "@/components/site/LegalPage";
import { pageMetadata } from "@/lib/seo";
import { site } from "@/lib/site";

export const metadata: Metadata = pageMetadata({
  title: "Privacy policy",
  description: "What data DataPilot processes, why, where it goes, how long it is kept and the choices you have.",
  path: "/privacy",
});

const sections: LegalSection[] = [
  {
    id: "who",
    title: "Who we are",
    body: (
      <p>
        This service is operated by {site.legalName} (&quot;we&quot;). We are responsible for the personal data described here. You can reach us through the{" "}
        <Link href="/contact">contact page</Link>
        {site.email ? <> or at <a href={`mailto:${site.email}`}>{site.email}</a></> : null}.
      </p>
    ),
  },
  {
    id: "data",
    title: "Data we process",
    body: (
      <>
        <ul>
          <li><strong>Account data:</strong> your email address, name, a password hash (scrypt, never the password itself), and if you turn it on, an encrypted two-factor secret and hashed recovery codes.</li>
          <li><strong>Your datasets:</strong> files you upload or import, the profiles and quality reports we compute from them, your questions and the answers, saved schedules and share links.</li>
          <li><strong>API keys you bring:</strong> held encrypted in server memory for the session only and never written to disk.</li>
          <li><strong>Messages you send us:</strong> the name, email address and message from the contact form.</li>
          <li><strong>Technical data:</strong> request and session identifiers, timings and error details in server logs. IP addresses are used in memory to apply rate limits.</li>
        </ul>
      </>
    ),
  },
  {
    id: "ai",
    title: "How AI processing works",
    body: (
      <>
        <p>
          To answer a question, DataPilot sends the language model provider configured for your workspace (Google Gemini, OpenAI or Anthropic) your question, a description of your datasets (table and column names, types and summary statistics) and the results of the queries it runs, which can include rows of your data. The calculations themselves run on our servers, not at the provider.
        </p>
        <p>
          Each provider processes this data under its own terms. If you add your own API key, your agreement with that provider applies. We do not use your data to train models, and we do not sell it.
        </p>
      </>
    ),
  },
  {
    id: "purposes",
    title: "Why we process it",
    body: (
      <ul>
        <li>To provide the service you asked for: storing your data, answering questions and running schedules (performance of a contract).</li>
        <li>To keep accounts and the service secure, prevent abuse and fix problems (legitimate interests).</li>
        <li>To send emails you need: account confirmation, password resets, security notices and schedule summaries you set up.</li>
        <li>To reply to messages you send us.</li>
        <li>With your consent only, to measure site usage with analytics, if analytics is enabled.</li>
      </ul>
    ),
  },
  {
    id: "retention",
    title: "How long we keep it",
    body: (
      <ul>
        <li>Workspaces you use without an account are deleted automatically after a period of inactivity, two hours by default, unless they have scheduled queries.</li>
        <li>Workspaces that belong to an account are kept until you delete them or your account.</li>
        <li>Sign-in tokens expire after 30 days by default. Email links expire after one hour (password reset) or one day (confirmation) and work once.</li>
        <li>Share links work until you revoke them or delete the workspace.</li>
      </ul>
    ),
  },
  {
    id: "cookies",
    title: "Cookies and browser storage",
    body: (
      <>
        <p>DataPilot does not use advertising cookies. It uses your browser&apos;s storage for things the service needs:</p>
        <ul>
          <li><strong>Session storage:</strong> your sign-in token, cleared when you close the tab.</li>
          <li><strong>Local storage:</strong> your last workspace, your light or dark theme, and your cookie choice.</li>
          {site.analyticsId ? (
            <li><strong>Analytics cookies (optional):</strong> Google Analytics cookies, set only if you choose &quot;Accept analytics&quot;. Choosing &quot;Essential only&quot; later stops analytics and removes these cookies.</li>
          ) : null}
        </ul>
        <p>You can change your choice at any time with &quot;Cookie settings&quot; in the footer.</p>
      </>
    ),
  },
  {
    id: "sharing",
    title: "Who we share it with",
    body: (
      <ul>
        <li>The language model provider used for your workspace, as described above.</li>
        <li>Our email delivery provider, to send the emails listed above.</li>
        <li>Hosting providers that run our servers.</li>
        <li>Authorities, where the law requires it.</li>
      </ul>
    ),
  },
  {
    id: "security",
    title: "Security",
    body: (
      <p>
        Passwords are hashed, two-factor secrets are encrypted, email links are stored only as hashes, workspaces are isolated per user, SQL is restricted to read-only queries, Python runs in a resource limited sandbox, and connectors refuse private network addresses by default. No system is perfectly secure; if you find a problem, please report it through the <Link href="/contact">contact page</Link>.
      </p>
    ),
  },
  {
    id: "rights",
    title: "Your rights",
    body: (
      <p>
        Depending on where you live, you may have the right to access, correct, export or delete your personal data, to object to or restrict processing, and to withdraw consent. You can delete workspaces and datasets yourself in the app. For anything else, choose &quot;Privacy request&quot; on the <Link href="/contact">contact page</Link>. You may also complain to your local data protection authority.
      </p>
    ),
  },
  {
    id: "changes",
    title: "Changes to this policy",
    body: <p>If we make material changes, we will update the effective date above and, where appropriate, notify account holders by email.</p>,
  },
];

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy policy"
      path="/privacy"
      lead="What we process, why, where it goes and how long we keep it, in plain language."
      effective={site.updated}
      sections={sections}
    />
  );
}
