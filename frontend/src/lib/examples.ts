import type { StaticImageData } from "next/image";
import analystChart from "@/assets/screenshots/analyst-chart.webp";
import anomalyExplanation from "@/assets/screenshots/anomaly-explanation.webp";
import dataOverview from "@/assets/screenshots/data-overview.webp";
import dataQuality from "@/assets/screenshots/data-quality.webp";

export interface Example {
  slug: string;
  title: string;
  question: string | null;
  before: { label: string; text: string };
  after: { label: string; image: StaticImageData; alt: string };
  outcome: string;
  feature: string;
}

const ORDERS = `order_id,order_date,customer_id,product_id,region,channel,quantity,unit_price,discount,revenue,status
100751,2023-01-01,97,19,North America,Online,2,103.77,0.0,207.54,Returned
101103,2023-01-01,525,8,North America,Online,2,1130.86,0.0,2261.72,Completed
103082,2023-01-01,547,11,Europe,Online,2,29.91,0.15,50.85,Completed
103720,2023-01-01,555,8,North America,Online,2,1136.63,0.05,2159.6,Completed
100480,2023-01-02,144,7,Europe,Retail,1,541.11,0.0,541.11,Completed
... 7,039 more rows`;

const HEADERS = `customers.csv  (600 rows)
customer_id,customer_name,segment,country,region,signup_date

orders.csv  (7,044 rows)
order_id,order_date,customer_id,product_id,region,channel,...

products.csv  (25 rows)
product_id,product_name,category,unit_cost,list_price`;

export const examples: Example[] = [
  {
    slug: "quality",
    title: "A raw export becomes a ranked list of problems",
    question: null,
    before: { label: "orders.csv as exported", text: ORDERS },
    after: { label: "Quality report generated on upload", image: dataQuality, alt: "Quality score of 84 with six issues ranked by severity, including a negative revenue value and 12 duplicate rows" },
    outcome: "A quality score of 84, one negative revenue value, 12 duplicate rows and missing channels, found before anyone built a chart on top of them.",
    feature: "data-quality",
  },
  {
    slug: "anomalies",
    title: "Thousands of rows become a short list of outliers with reasons",
    question: "Which region has the highest revenue? Show a chart and check the revenue column for anomalies.",
    before: { label: "orders.csv, 7,044 rows", text: ORDERS },
    after: { label: "Anomaly explanation with the flagged rows", image: anomalyExplanation, alt: "Anomaly card showing IQR fences, quartiles, high severity and a table of flagged orders" },
    outcome: "492 values outside the IQR fences, with the quartiles, the bounds and the most extreme order listed so each one can be checked.",
    feature: "anomaly-detection",
  },
  {
    slug: "chart",
    title: "A question becomes a chart with the query behind it",
    question: "Which region has the highest revenue? Show a chart and check the revenue column for anomalies.",
    before: { label: "orders.csv, 7,044 rows", text: ORDERS },
    after: { label: "Answer and chart computed by SQL", image: analystChart, alt: "Answer naming North America as the highest revenue region, with tool calls for SQL, chart and anomaly detection and a bar chart of revenue by region" },
    outcome: "North America leads at 3,275,899.34. The figure, the chart and the anomaly check each come from a tool call that ran in milliseconds, and the SQL sits under the answer.",
    feature: "charts",
  },
  {
    slug: "joins",
    title: "Three separate files become one connected model",
    question: null,
    before: { label: "Three CSV files, no declared keys", text: HEADERS },
    after: { label: "Overview with inferred relationships", image: dataOverview, alt: "Dataset overview with metrics, histograms and relationships between orders, customers and products" },
    outcome: "orders.customer_id and orders.product_id matched to their tables with 100% key overlap and the right cardinality, ready for cross-file questions.",
    feature: "multi-file-joins",
  },
];
