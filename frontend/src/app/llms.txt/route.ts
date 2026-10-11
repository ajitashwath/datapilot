import { posts } from "@/lib/blog";
import { features } from "@/lib/features";
import { absoluteUrl, site } from "@/lib/site";

export const dynamic = "force-static";

export function GET() {
  const link = (title: string, path: string, note: string) => `- [${title}](${absoluteUrl(path)}): ${note}`;
  const lines = [
    `# ${site.name}`,
    "",
    `> ${site.description}`,
    "",
    "DataPilot separates planning from computation: a language model interprets the question and writes SQL or Python, deterministic tools (DuckDB, pandas, statistics code) execute it on the user's data, and every number in an answer is traceable to a tool result. A grounding check flags figures that no tool produced.",
    "",
    "## Features",
    "",
    ...features.map((f) => link(f.name, `/features/${f.slug}`, f.summary)),
    "",
    "## Guides",
    "",
    ...posts.map((p) => link(p.title, `/blog/${p.slug}`, p.description)),
    "",
    "## Company",
    "",
    link("About", "/about", "Principles and architecture"),
    link("Before and after examples", "/examples", "Sample files and the output DataPilot produced from them"),
    link("Contact", "/contact", "Questions, security reports and privacy requests"),
    "",
    "## Optional",
    "",
    link("Privacy policy", "/privacy", "What data is processed and where it goes"),
    link("Terms of service", "/terms", "Terms of use"),
    ...site.social.filter((s) => s.name === "GitHub").map((s) => `- [Source code](${s.url}): Repository and documentation`),
    "",
  ];
  return new Response(lines.join("\n"), { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
