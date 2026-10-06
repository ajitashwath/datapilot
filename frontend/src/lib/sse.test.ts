import { describe, expect, it } from "vitest";
import { parseSseChunk } from "./sse";
import { applyEvent, newAssistantMessage } from "./chatState";

describe("parseSseChunk", () => {
  it("parses complete events and keeps the partial remainder", () => {
    const first = 'event: text\ndata: {"type":"text","step":0,"delta":"Hi"}\n\nevent: text\ndata: {"type":"te';
    const { events, rest } = parseSseChunk(first);
    expect(events).toEqual([{ type: "text", step: 0, delta: "Hi" }]);
    const second = parseSseChunk(rest + 'xt","step":0,"delta":"!"}\n\n');
    expect(second.events).toEqual([{ type: "text", step: 0, delta: "!" }]);
    expect(second.rest).toBe("");
  });

  it("ignores malformed events", () => {
    const { events } = parseSseChunk("event: text\ndata: {not json}\n\n");
    expect(events).toEqual([]);
  });
});

describe("applyEvent", () => {
  it("accumulates text per step and attaches tool results to their call", () => {
    let message = newAssistantMessage("a1");
    message = applyEvent(message, { type: "text", step: 0, delta: "Look" });
    message = applyEvent(message, { type: "text", step: 0, delta: "ing" });
    message = applyEvent(message, { type: "tool_call", step: 0, id: "t1", name: "execute_sql", input: {} });
    message = applyEvent(message, {
      type: "tool_result",
      step: 0,
      id: "t1",
      name: "execute_sql",
      duration_ms: 5,
      result: { ok: true, data: {}, error: null, sql: "SELECT 1", code: null, table: null, chart: null, anomalies: [] },
    });
    message = applyEvent(message, { type: "text", step: 1, delta: "Done" });
    message = applyEvent(message, { type: "done", tools_used: ["execute_sql"], warnings: [], duration_ms: 10 });
    expect(message.steps.map((s) => s.kind)).toEqual(["text", "tool", "text"]);
    const tool = message.steps[1];
    expect(tool.kind === "tool" && tool.result?.sql).toBe("SELECT 1");
    expect(message.status).toBe("done");
  });

  it("marks the message as failed on error events", () => {
    const message = applyEvent(newAssistantMessage("a2"), { type: "error", message: "boom" });
    expect(message.status).toBe("error");
    expect(message.error).toBe("boom");
  });
});
