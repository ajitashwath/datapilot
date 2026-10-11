export const faqs = [
  {
    q: "What data can I analyse?",
    a: "Upload CSV files (50 MB each by default), or import from a CSV link, a Google Sheet shared by link, a SQLite file or a read-only Postgres connection. Several files can be analysed together.",
  },
  {
    q: "Does the AI calculate the numbers?",
    a: "No. The language model plans the analysis and writes SQL or Python. DuckDB and pandas run that code on your data, and the answer quotes their results. The code is shown under every answer.",
  },
  {
    q: "What if an answer contains a number that no query produced?",
    a: "After each answer, numbers in the text are compared with the tool results. Anything without a source is flagged, so you know to check it before relying on it.",
  },
  {
    q: "Which AI models does it use?",
    a: "Gemini, OpenAI and Anthropic models are supported. You can use the server's key or bring your own key for a session. Keys you bring are kept encrypted in memory and never written to disk.",
  },
  {
    q: "Is my data used to train models?",
    a: "DataPilot does not use your data to train models. To answer a question, it sends the question, a description of your datasets and query results to the model provider you choose, which processes them under its own terms.",
  },
  {
    q: "Can I use it with my team?",
    a: "Yes. With accounts enabled you get private workspaces, teams with admin, member and viewer roles, share links, scheduled reports, two-factor sign-in and single sign-on.",
  },
];
