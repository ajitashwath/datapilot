import { describe, expect, it } from "vitest";
import { applyEvent, finalText, messagesFromTranscript, newAssistantMessage } from "./chatState";
import { buildReport, tableToCsv } from "./export";
import type { StreamEvent, ToolResult } from "./types";

const toolResult = (overrides: Partial<ToolResult>): ToolResult => ({
  ok: true, data: {}, error: null, sql: null, code: null, table: null, chart: null, anomalies: [], ...overrides,
});

describe("tableToCsv", () => {
  it("quotes commas, quotes and newlines", () => {
    const csv = tableToCsv({ columns: ["name", "note"], rows: [["a,b", 'say "hi"'], ["x", "line1\nline2"]], row_count: 2, truncated: false });
    expect(csv).toBe('name,note\n"a,b","say ""hi"""\nx,"line1\nline2"\n');
  });

  it("neutralises spreadsheet formulas", () => {
    const csv = tableToCsv({ columns: ["v"], rows: [["=SUM(A1:A9)"], ["+1"], ["@cmd"], ["-5"], [42]], row_count: 5, truncated: false });
    expect(csv.split("\n").slice(1, 5)).toEqual(["'=SUM(A1:A9)", "'+1", "'@cmd", "'-5"]);
    expect(csv).toContain("\n42\n");
  });
});

describe("transcript and report", () => {
  const events: StreamEvent[] = [
    { type: "text", step: 0, delta: "Checking. " },
    { type: "tool_call", step: 0, id: "t1", name: "execute_sql", input: {} },
    {
      type: "tool_result", step: 0, id: "t1", name: "execute_sql", duration_ms: 4,
      result: toolResult({ sql: "SELECT 1 AS one", table: { columns: ["one"], rows: [[1]], row_count: 1, truncated: false } }),
    },
    { type: "text", step: 1, delta: "The answer is **1**." },
    { type: "done", tools_used: ["execute_sql"], warnings: ["check 9,999"], duration_ms: 20 },
  ];

  it("rebuilds messages from a stored transcript", () => {
    const messages = messagesFromTranscript([{ question: "What is one?", events }]);
    expect(messages.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(messages[1].status).toBe("done");
    expect(finalText(messages[1])).toBe("The answer is **1**.");
  });

  it("marks a transcript that never finished as done instead of streaming forever", () => {
    const [, assistant] = messagesFromTranscript([{ question: "q", events: events.slice(0, 2) }]);
    expect(assistant.status).toBe("done");
  });

  it("builds a markdown report with the answer, table, SQL and warnings", () => {
    const report = buildReport(messagesFromTranscript([{ question: "What is one?", events }]), "Test report");
    expect(report).toContain("# Test report");
    expect(report).toContain("## What is one?");
    expect(report).toContain("The answer is **1**.");
    expect(report).toContain("| one |");
    expect(report).toContain("```sql\nSELECT 1 AS one\n```");
    expect(report).toContain("> check 9,999");
  });

  it("keeps errors visible after a replay", () => {
    const message = applyEvent(newAssistantMessage("x"), { type: "error", message: "boom" });
    expect(message.status).toBe("error");
  });
});
