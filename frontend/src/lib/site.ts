const read = (value: string | undefined) => (value ?? "").trim();

export interface SocialLink {
  name: "GitHub" | "LinkedIn" | "X";
  url: string;
}

export interface HoursRule {
  days: string[];
  opens: string;
  closes: string;
}

const DAY_CODES = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"] as const;
const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const RULE_PATTERN = /^([A-Z][a-z])(?:-([A-Z][a-z]))?\s+([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-4]):([0-5]\d)$/;

export function parseHours(spec: string): HoursRule[] {
  const rules: HoursRule[] = [];
  for (const part of spec.split(",").map((p) => p.trim()).filter(Boolean)) {
    const match = RULE_PATTERN.exec(part);
    if (!match) return [];
    const start = DAY_CODES.indexOf(match[1] as (typeof DAY_CODES)[number]);
    const end = match[2] ? DAY_CODES.indexOf(match[2] as (typeof DAY_CODES)[number]) : start;
    const opens = `${match[3]}:${match[4]}`;
    const closes = `${match[5]}:${match[6]}`;
    if (start < 0 || end < start || closes <= opens) return [];
    rules.push({ days: DAY_NAMES.slice(start, end + 1), opens, closes });
  }
  return rules;
}

export function describeDays(days: string[]): string {
  return days.length === 1 ? days[0] : `${days[0]} to ${days[days.length - 1]}`;
}

export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, "")}`;
}

function socialLinks(): SocialLink[] {
  const links: SocialLink[] = [
    { name: "GitHub", url: read(process.env.NEXT_PUBLIC_GITHUB_URL) || "https://github.com/ajitashwath/datapilot" },
    { name: "LinkedIn", url: read(process.env.NEXT_PUBLIC_LINKEDIN_URL) },
    { name: "X", url: read(process.env.NEXT_PUBLIC_X_URL) },
  ];
  return links.filter((link) => /^https:\/\/[^\s]+$/.test(link.url));
}

export const site = {
  name: "DataPilot",
  url: (read(process.env.NEXT_PUBLIC_SITE_URL) || "http://localhost:3000").replace(/\/+$/, ""),
  tagline: "Verified answers from your data",
  description:
    "DataPilot is an AI data analyst for CSV files and databases. Ask questions in plain English and get answers, charts and anomaly explanations computed by SQL and Python on your real data, with the code shown.",
  email: read(process.env.NEXT_PUBLIC_CONTACT_EMAIL),
  phone: read(process.env.NEXT_PUBLIC_CONTACT_PHONE),
  hours: parseHours(read(process.env.NEXT_PUBLIC_SUPPORT_HOURS)),
  hoursSpec: read(process.env.NEXT_PUBLIC_SUPPORT_HOURS),
  timezone: read(process.env.NEXT_PUBLIC_SUPPORT_TIMEZONE) || "UTC",
  legalName: read(process.env.NEXT_PUBLIC_LEGAL_NAME) || "DataPilot",
  jurisdiction: read(process.env.NEXT_PUBLIC_LEGAL_JURISDICTION),
  googleVerification: read(process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION),
  analyticsId: /^G-[A-Z0-9]+$/.test(read(process.env.NEXT_PUBLIC_GA_ID)) ? read(process.env.NEXT_PUBLIC_GA_ID) : "",
  social: socialLinks(),
  updated: "2026-10-11",
};

export const absoluteUrl = (path: string) => `${site.url}${path === "/" ? "" : path}`;
