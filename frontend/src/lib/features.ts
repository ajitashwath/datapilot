import type { StaticImageData } from "next/image";
import analystChart from "@/assets/screenshots/analyst-chart.webp";
import anomalyExplanation from "@/assets/screenshots/anomaly-explanation.webp";
import dataOverview from "@/assets/screenshots/data-overview.webp";
import dataQuality from "@/assets/screenshots/data-quality.webp";
import landing from "@/assets/screenshots/landing.webp";

export interface Feature {
  slug: string;
  name: string;
  headline: string;
  summary: string;
  intro: string;
  points: { title: string; body: string }[];
  steps: string[];
  faqs: { q: string; a: string }[];
  image: StaticImageData;
  imageAlt: string;
}

export const features: Feature[] = [
  {
    slug: "natural-language-analysis",
    name: "Natural language analysis",
    headline: "Ask in plain English. Get the number, the query and the reasoning.",
    summary: "Rankings, trends, comparisons and averages computed by SQL on your data.",
    intro:
      "Type a question the way you would ask a colleague. DataPilot plans the analysis, writes the SQL or Python, runs it on your files and explains the result. The model never does the arithmetic, so the figures in the answer are the figures the query returned.",
    points: [
      { title: "Follow-up questions that remember context", body: "Ask \"show me its monthly trend\" after a ranking and DataPilot keeps the region, product or filter you were looking at." },
      { title: "The work is always shown", body: "Every answer carries the SQL or Python that produced it, ready to copy, rerun or schedule." },
      { title: "Grounding check on every answer", body: "Numbers in the written answer are compared with the tool results. Anything that does not match is flagged before you rely on it." },
    ],
    steps: ["Upload a CSV or connect a source", "Ask a question in your own words", "Read the answer, then check the query underneath it"],
    faqs: [
      { q: "Does the AI calculate the numbers?", a: "No. The language model plans and writes queries. DuckDB and pandas execute them on your data, and the answer quotes their results." },
      { q: "Which language models are supported?", a: "Gemini, OpenAI and Anthropic models. You can use the server's key or bring your own key for a session." },
    ],
    image: landing,
    imageAlt: "DataPilot analyst view with suggested questions generated from the dataset schema",
  },
  {
    slug: "charts",
    name: "Charts",
    headline: "Charts drawn from executed queries, not from a model's memory.",
    summary: "Bar, line, pie, scatter and histogram charts with the data behind them.",
    intro:
      "Ask for a chart and DataPilot runs the aggregation in SQL, then renders the result. Switch between bar, line and pie in place, open the underlying table, or export it as CSV.",
    points: [
      { title: "Five chart types", body: "Bar, line with multiple series, pie, scatter and histogram cover rankings, trends, shares, relationships and distributions." },
      { title: "Data you can inspect", body: "Every chart has a \"view chart data\" table built from the same query result." },
      { title: "Readable in light and dark", body: "Charts follow the interface theme and stay legible at phone widths." },
    ],
    steps: ["Ask for a comparison or a trend", "DataPilot picks a chart type that fits the shape of the result", "Switch type, inspect the data or export it"],
    faqs: [
      { q: "Can I change the chart type after it is drawn?", a: "Yes. Bar, line and pie charts can be switched in place without asking again." },
      { q: "Where do the chart values come from?", a: "From a SQL query that ran on your data. The query is shown under the chart." },
    ],
    image: analystChart,
    imageAlt: "Answer with a bar chart of revenue by region and the tool calls that computed it",
  },
  {
    slug: "anomaly-detection",
    name: "Anomaly detection",
    headline: "Find the outliers, and the reason each one was flagged.",
    summary: "IQR, z-score and time aware checks with a computed explanation.",
    intro:
      "DataPilot checks numeric columns with three methods: interquartile range fences, z-scores and a rolling median for time series. Every result includes the affected rows, the bounds that were used and a severity, all computed from the statistics rather than written by the model.",
    points: [
      { title: "Three complementary methods", body: "IQR is robust to skew, z-score suits roughly normal data, and the rolling median catches spikes relative to recent history." },
      { title: "Explanations with numbers", body: "You see the quartiles, the fences and how far the most extreme value sits beyond them." },
      { title: "The rows, not just a count", body: "Flagged records are listed so you can open them and decide whether they are errors or real events." },
    ],
    steps: ["Ask DataPilot to look for anomalies in a column", "Review the method, bounds and severity", "Open the flagged rows and follow up with a question"],
    faqs: [
      { q: "Which method should I use?", a: "Start with IQR for skewed business data such as revenue. Use the time aware method when the column has a date dimension and seasonality." },
      { q: "Are anomalies automatically removed?", a: "No. DataPilot reports them. Your data is never changed by an anomaly check." },
    ],
    image: anomalyExplanation,
    imageAlt: "Anomaly card for revenue showing IQR fences, severity and the flagged rows",
  },
  {
    slug: "data-quality",
    name: "Data quality reports",
    headline: "Know what is wrong with a file before you trust an answer from it.",
    summary: "A 0 to 100 score with missing values, duplicates and type problems explained.",
    intro:
      "When a file is loaded, DataPilot profiles every column and runs a set of quality checks. The result is a score and a ranked list of issues, each with the column, the count and the share of rows affected.",
    points: [
      { title: "Broad checks", body: "Missing values, duplicate rows, numbers stored as text, unparseable dates, inconsistent categories, constant columns, high cardinality and suspicious values." },
      { title: "Severity you can act on", body: "Issues are graded high, medium or low and sorted, so the problems most likely to distort an answer come first." },
      { title: "Profiles for every column", body: "Types, ranges, top values, cardinality and a preview in the Data explorer." },
    ],
    steps: ["Upload a file", "Open Data explorer, then Quality", "Fix the source or ask DataPilot to account for the issue"],
    faqs: [
      { q: "How is the score calculated?", a: "A file starts at 100 and each issue subtracts a fixed penalty for its severity, so high severity issues cost the most. A file with no issues scores 100." },
      { q: "What about malformed rows?", a: "Rows that cannot be parsed are skipped and reported at upload instead of failing the whole file." },
    ],
    image: dataQuality,
    imageAlt: "Data quality report with a score of 84 and six issues ranked by severity",
  },
  {
    slug: "multi-file-joins",
    name: "Multi-file analysis",
    headline: "Join your files without double counting.",
    summary: "Relationships between CSVs are detected, checked and used safely.",
    intro:
      "Upload customers, orders and products together and DataPilot infers how they relate from column names and value overlap, including the cardinality of each link. That knowledge is given to the model with explicit guidance to avoid fan-out, the classic mistake that inflates totals after a join.",
    points: [
      { title: "Inferred relationships", body: "Keys are matched by name and by how many values overlap, then labelled one-to-one, one-to-many or many-to-one." },
      { title: "Manual control", body: "Declare a join yourself when the names do not match or the inference is not what you want." },
      { title: "Fan-out awareness", body: "Aggregations are planned so a one-to-many join does not repeat a value it should count once." },
    ],
    steps: ["Upload related files together", "Review the relationships in the sidebar", "Ask questions that span files"],
    faqs: [
      { q: "Do the column names have to match?", a: "No. Name similarity helps, but value overlap is checked too, and you can declare a join manually." },
      { q: "How many files can a workspace hold?", a: "The limit is set by the server administrator. The default allows several files per workspace." },
    ],
    image: dataOverview,
    imageAlt: "Dataset overview with key metrics, histograms and inferred relationships",
  },
  {
    slug: "data-connectors",
    name: "Data connectors",
    headline: "Bring data from where it already lives.",
    summary: "CSV links, Google Sheets, SQLite files and read-only Postgres.",
    intro:
      "Besides file upload, DataPilot can import from a CSV link, a Google Sheet shared by link, a SQLite file or a read-only Postgres connection. Imports run in the background with progress, and linked sources can be refreshed later.",
    points: [
      { title: "Refreshable links", body: "Datasets imported from a link remember their source and can be refreshed on demand or before a scheduled query." },
      { title: "Safe by default", body: "Connectors refuse private network addresses unless an administrator allows them, which blocks server-side request forgery." },
      { title: "Large data handled on disk", body: "Uploads stream to disk and DuckDB spills to disk, so files do not have to fit in memory." },
    ],
    steps: ["Choose \"Add from a link, SQLite or Postgres\"", "Paste the link or connection details", "Watch the import progress, then start asking"],
    faqs: [
      { q: "Is Postgres access read-only?", a: "Yes. DataPilot imports the tables you choose and never writes to your database." },
      { q: "Are connection details stored?", a: "The password is used for the import only. The workspace records the host, database and table so you know where the data came from." },
    ],
    image: dataOverview,
    imageAlt: "Dataset overview with key metrics and distributions, the view every imported dataset gets",
  },
  {
    slug: "scheduled-queries",
    name: "Scheduled queries",
    headline: "Turn a good answer into a recurring report.",
    summary: "Run saved SQL hourly, daily or weekly with email and webhook alerts.",
    intro:
      "Any query from an answer can be saved as a schedule. DataPilot runs it on time, keeps the latest results and can email a summary or call a webhook, either every time or only when a run fails.",
    points: [
      { title: "Flexible timing", body: "Hourly, daily or weekly runs, plus a manual \"run now\" whenever you need it." },
      { title: "Fresh data first", body: "Schedules can re-download linked datasets before running, so reports reflect the latest source." },
      { title: "Alerts without the data", body: "Email summaries describe the run without attaching your data." },
    ],
    steps: ["Click Schedule under any SQL query", "Pick a frequency and notifications", "Find results under Data explorer, Schedules"],
    faqs: [
      { q: "What is the shortest interval?", a: "The administrator sets a minimum. The default is 15 minutes." },
      { q: "Do scheduled workspaces expire?", a: "No. Workspaces with schedules are exempt from automatic expiry." },
    ],
    image: anomalyExplanation,
    imageAlt: "Answer with its SQL query and a Schedule button underneath",
  },
  {
    slug: "teams-and-sharing",
    name: "Teams and sharing",
    headline: "Work together without giving everyone everything.",
    summary: "Private workspaces, team roles, read-only viewers and share links.",
    intro:
      "With accounts enabled, every user has private workspaces that other people cannot even detect. Teams add admin, member and viewer roles, and share links publish a frozen, read-only snapshot of a conversation that you can revoke at any time.",
    points: [
      { title: "Roles that mean something", body: "Viewers get a genuinely read-only workspace. Members can analyse. Admins manage the team." },
      { title: "Share links", body: "An unguessable URL shows answers, tables, charts and SQL to people without an account." },
      { title: "Enterprise sign-in", body: "Email and password with two-factor authentication, or single sign-on through OpenID Connect." },
    ],
    steps: ["Create a team and invite colleagues", "Move a workspace into the team", "Share a snapshot with anyone who needs to see the result"],
    faqs: [
      { q: "Can I revoke a share link?", a: "Yes. Revoking a link makes it stop working immediately." },
      { q: "Is two-factor authentication supported?", a: "Yes. Authenticator app codes and single use recovery codes are supported." },
    ],
    image: landing,
    imageAlt: "DataPilot workspace with datasets, relationships and the analyst view",
  },
];

export const featureBySlug = (slug: string) => features.find((f) => f.slug === slug);
