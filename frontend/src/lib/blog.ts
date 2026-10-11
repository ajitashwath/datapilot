export type Block =
  | { kind: "p"; text: string }
  | { kind: "h2"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "code"; lang: string; text: string }
  | { kind: "note"; text: string };

export interface Post {
  slug: string;
  title: string;
  description: string;
  published: string;
  minutes: number;
  tags: string[];
  body: Block[];
}

export const posts: Post[] = [
  {
    slug: "why-your-ai-analyst-should-never-do-the-maths",
    title: "Why your AI analyst should never do the maths",
    description: "Language models are good at planning an analysis and bad at arithmetic. Here is how to split the work so every number can be checked.",
    published: "2026-10-06",
    minutes: 6,
    tags: ["Product", "Accuracy"],
    body: [
      { kind: "p", text: "Ask a general purpose chatbot for the average order value in a spreadsheet and you will usually get a confident, well formatted number. Sometimes it is right. The problem is that you cannot tell which times." },
      { kind: "p", text: "Large language models predict text. When they produce \"the average is 412.37\" they are generating characters that look like a plausible answer, not running a calculation. On small tables they often get close. On real business data, with thousands of rows, filters and joins, they drift, and nothing in the answer tells you it drifted." },
      { kind: "h2", text: "Split planning from computing" },
      { kind: "p", text: "DataPilot gives each part of the job to the component that is good at it. The model reads your question and the schema, decides what needs to be computed and writes a query. A database engine runs that query on the actual rows. The model then explains the result it was handed." },
      { kind: "list", items: ["The model plans: which tables, which filters, which aggregation.", "DuckDB or a sandboxed Python process executes: every sum, average and count.", "The model explains: it describes the result, quoting the numbers the tool returned."] },
      { kind: "code", lang: "sql", text: "SELECT channel, ROUND(SUM(revenue), 2) AS total_revenue\nFROM orders\nGROUP BY channel\nORDER BY total_revenue DESC;" },
      { kind: "p", text: "Because the query is shown under the answer, anyone can read it, rerun it, or paste it into another tool. If the model misunderstood the question, you see that in the SQL rather than discovering it in a board meeting." },
      { kind: "h2", text: "Check the answer against the evidence" },
      { kind: "p", text: "Separating the steps is most of the battle, but a model can still restate a number incorrectly when it writes the explanation. So DataPilot runs a grounding check after every answer: numbers in the written text are compared with the numbers that appeared in tool results, and anything that has no source is flagged to you." },
      { kind: "note", text: "A flagged number is not necessarily wrong. It might be a rounded figure or a simple difference of two results. The point is that you know it was not read directly from a query, so you can decide whether to trust it." },
      { kind: "h2", text: "What this means in practice" },
      { kind: "p", text: "You still get the convenience of asking in plain English. What changes is the failure mode. Instead of a plausible but silent error, a mistake shows up as a visible query you can inspect. That is the difference between an assistant you have to double check by hand and one whose work you can audit in seconds." },
    ],
  },
  {
    slug: "iqr-vs-z-score-vs-rolling-median",
    title: "IQR, z-score or rolling median: choosing an anomaly method",
    description: "Three common ways to flag outliers, what each one assumes, and when to reach for which on business data.",
    published: "2026-09-29",
    minutes: 7,
    tags: ["Statistics", "Anomalies"],
    body: [
      { kind: "p", text: "\"Show me anything unusual in revenue\" sounds like one question, but there are several reasonable definitions of unusual. The method you choose decides which rows get flagged, so it is worth knowing what each one assumes." },
      { kind: "h2", text: "Interquartile range (IQR)" },
      { kind: "p", text: "Sort the values and take the 25th percentile (Q1) and the 75th percentile (Q3). The interquartile range is Q3 minus Q1. Values below Q1 minus k times IQR or above Q3 plus k times IQR are outliers. The usual k is 1.5; a k of 3 flags only extreme values." },
      { kind: "list", items: ["Works well on skewed data such as revenue, order size or session length.", "Not distorted by the outliers themselves, because quartiles barely move when a few huge values appear.", "Ignores time, so a value that is normal in December but strange in March is treated the same in both months."] },
      { kind: "h2", text: "Z-score" },
      { kind: "p", text: "Subtract the mean and divide by the standard deviation. A z-score above 3 or below minus 3 is commonly treated as an outlier." },
      { kind: "list", items: ["Easy to interpret when data is roughly bell shaped, such as measurement errors or test scores.", "Fragile on skewed data, because the extreme values inflate the standard deviation and hide themselves.", "Also ignores time."] },
      { kind: "h2", text: "Rolling median" },
      { kind: "p", text: "For a time series, compare each point with the median of the points around it, and scale the difference by a robust measure of spread such as the median absolute deviation. A value is unusual if it is far from its own neighbourhood." },
      { kind: "list", items: ["Respects trends and seasonality: steady growth does not trigger alerts.", "Catches spikes and drops that are normal in size overall but wrong for that moment.", "Needs a date column and enough history to form a window."] },
      { kind: "h2", text: "A practical default" },
      { kind: "p", text: "For most business metrics, start with IQR on the raw values. If the metric has a date dimension, aggregate it by day or week and use the rolling median. Reserve the z-score for measurements you expect to be symmetric." },
      { kind: "note", text: "Whichever method you use, look at the flagged rows before acting. An outlier is a question, not a verdict. A huge order might be fraud, a data entry error, or your best customer." },
      { kind: "p", text: "DataPilot reports the method, the bounds, the number of rows flagged and a severity with every anomaly result, so you can see exactly which definition of unusual produced the list." },
    ],
  },
  {
    slug: "csv-data-quality-checklist",
    title: "A data quality checklist for CSV files",
    description: "Eight problems that quietly break analyses of exported spreadsheets, and how to spot each one before it reaches a chart.",
    published: "2026-09-22",
    minutes: 6,
    tags: ["Data quality", "Guides"],
    body: [
      { kind: "p", text: "CSV is the most common way data moves between systems, and also one of the least forgiving. There is no schema, no types and no validation. These are the issues we see most often, roughly in order of how much damage they do." },
      { kind: "h2", text: "1. Rows that do not parse" },
      { kind: "p", text: "A stray quote or an unescaped delimiter shifts every following column in that row. Count the rows you expected and compare with the rows you loaded." },
      { kind: "h2", text: "2. Numbers stored as text" },
      { kind: "p", text: "Currency symbols, thousands separators and trailing spaces turn a numeric column into text. Sums silently skip those values or fail outright." },
      { kind: "h2", text: "3. Dates that are not dates" },
      { kind: "p", text: "Mixed formats such as 03/04/2026 and 2026-04-03 in the same column are ambiguous. Check how many values fail to parse and which format the rest use." },
      { kind: "h2", text: "4. Missing values" },
      { kind: "p", text: "Empty cells, \"N/A\", \"null\" and \"-\" can all mean missing. Know the share per column, because an average over 60% of rows is a different number from an average over all of them." },
      { kind: "h2", text: "5. Duplicate rows" },
      { kind: "p", text: "Exports that were appended twice double every total. Exact duplicate rows are easy to count and almost always a mistake." },
      { kind: "h2", text: "6. Inconsistent categories" },
      { kind: "p", text: "\"North America\", \"north america\" and \"North America \" become three groups in a breakdown. Normalise case and whitespace before grouping." },
      { kind: "h2", text: "7. Suspicious values" },
      { kind: "p", text: "A negative quantity, a price of zero or an age of 212 might be a refund, a free item or a typo. Flag them and decide deliberately." },
      { kind: "h2", text: "8. Columns that carry no information" },
      { kind: "p", text: "A column with one constant value adds nothing. A column where almost every value is distinct is usually an identifier or free text and should not be used for grouping." },
      { kind: "note", text: "DataPilot runs all of these checks when a file is loaded and summarises them as a score from 0 to 100, with each issue listed by severity in Data explorer, Quality." },
    ],
  },
  {
    slug: "joining-csv-files-without-double-counting",
    title: "Joining CSV files without double counting",
    description: "Fan-out is the most common reason totals look too big after a join. How it happens, how to detect it and how to write the query correctly.",
    published: "2026-09-15",
    minutes: 7,
    tags: ["SQL", "Guides"],
    body: [
      { kind: "p", text: "You have an orders file and a lookup file such as products or customers. You join them, sum a column, and the total is far larger than it should be. Nothing errored. The join simply repeated rows." },
      { kind: "h2", text: "What fan-out is" },
      { kind: "p", text: "When one row on the left matches several rows on the right, the join produces one output row per match. Any value from the left side is repeated for each match. Sum it, and it is counted several times." },
      { kind: "code", lang: "sql", text: "SELECT p.category, SUM(p.list_price) AS catalogue_value\nFROM products p\nJOIN orders o ON o.product_id = p.product_id\nGROUP BY p.category;" },
      { kind: "p", text: "This query is meant to add up the list prices in the catalogue, but it sums each product's price once per order. On the sample data that turns a catalogue worth 11,417 into 3,448,782, because each product appears once per order." },
      { kind: "h2", text: "Know the cardinality of every join" },
      { kind: "list", items: ["One-to-one: each key appears once on both sides. Safe to sum either side.", "One-to-many: a customer has many orders. Sum values from the many side only, or aggregate the many side first.", "Many-to-many: almost always a sign that a join key is missing or wrong."] },
      { kind: "h2", text: "Aggregate before you join" },
      { kind: "code", lang: "sql", text: "WITH order_totals AS (\n  SELECT customer_id, SUM(revenue) AS revenue\n  FROM orders\n  GROUP BY customer_id\n)\nSELECT c.segment, SUM(t.revenue) AS revenue\nFROM customers c\nJOIN order_totals t ON t.customer_id = c.customer_id\nGROUP BY c.segment;" },
      { kind: "p", text: "Collapsing orders to one row per customer first turns the join into one-to-one, so nothing can repeat." },
      { kind: "h2", text: "A quick test" },
      { kind: "p", text: "After any join, compare the row count and a key total with the source table. If the joined total of orders.revenue differs from the total in orders alone, a join is filtering or repeating rows." },
      { kind: "note", text: "DataPilot infers relationships from column names and value overlap, labels each one with its cardinality, and gives the model explicit guidance to avoid fan-out when it writes multi-table queries. You can also declare a join manually." },
    ],
  },
  {
    slug: "from-one-off-question-to-scheduled-report",
    title: "From a one-off question to a scheduled report",
    description: "How to turn an answer you trust into a recurring report with alerts, and what to check before you automate it.",
    published: "2026-09-08",
    minutes: 5,
    tags: ["Workflows", "Scheduling"],
    body: [
      { kind: "p", text: "The most useful analyses get asked again: weekly revenue by channel, daily failed payments, the number of orders still pending after three days. Rewriting the same question every Monday is a waste, and copying numbers into a spreadsheet invites mistakes." },
      { kind: "h2", text: "Start from a verified answer" },
      { kind: "p", text: "Ask the question once and read the SQL under the answer. Check the filters, the date range and the grouping. If something is off, ask a follow-up until the query is exactly what you mean. A schedule repeats whatever the query does, including its mistakes." },
      { kind: "h2", text: "Make the date range relative" },
      { kind: "p", text: "A query that says WHERE order_date >= '2026-09-01' will return the same rows forever. Use a relative window so every run covers the right period." },
      { kind: "code", lang: "sql", text: "SELECT channel, SUM(revenue) AS revenue\nFROM orders\nWHERE order_date >= CURRENT_DATE - INTERVAL 7 DAY\nGROUP BY channel\nORDER BY revenue DESC;" },
      { kind: "h2", text: "Choose the right frequency and alert" },
      { kind: "list", items: ["Hourly for operational checks such as failed payments.", "Daily for dashboards people read every morning.", "Weekly for summaries and trends.", "Alert on every run when people rely on the summary, or only on failure when the schedule mainly keeps data fresh."] },
      { kind: "h2", text: "Keep the source fresh" },
      { kind: "p", text: "If the dataset came from a link or a shared Google Sheet, let the schedule re-download it before running. Otherwise the report will faithfully repeat last week's data." },
      { kind: "note", text: "In DataPilot, click Schedule under any SQL query, pick hourly, daily or weekly, and choose email or webhook notifications. Results of recent runs are kept under Data explorer, Schedules, and you can trigger a run manually at any time." },
    ],
  },
];

export const postBySlug = (slug: string) => posts.find((p) => p.slug === slug);

export function formatDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}
