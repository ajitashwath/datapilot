import type { ChatMessage, StreamEvent } from "./types";

export function newAssistantMessage(id: string): ChatMessage {
  return { id, role: "assistant", text: "", steps: [], status: "streaming", warnings: [] };
}

export function applyEvent(message: ChatMessage, event: StreamEvent): ChatMessage {
  const steps = [...message.steps];
  switch (event.type) {
    case "text": {
      const last = steps[steps.length - 1];
      if (last && last.kind === "text" && last.step === event.step) {
        steps[steps.length - 1] = { ...last, text: last.text + event.delta };
      } else {
        steps.push({ kind: "text", step: event.step, text: event.delta });
      }
      return { ...message, steps };
    }
    case "tool_call":
      steps.push({ kind: "tool", id: event.id, name: event.name, input: event.input });
      return { ...message, steps };
    case "tool_result": {
      const index = steps.findIndex((s) => s.kind === "tool" && s.id === event.id);
      if (index >= 0) {
        const step = steps[index];
        if (step.kind === "tool") steps[index] = { ...step, result: event.result, durationMs: event.duration_ms };
      }
      return { ...message, steps };
    }
    case "done":
      return { ...message, status: "done", warnings: event.warnings, durationMs: event.duration_ms };
    case "error":
      return { ...message, status: "error", error: event.message };
  }
}

export function finalText(message: ChatMessage): string {
  const lastTool = message.steps.map((s) => s.kind).lastIndexOf("tool");
  return message.steps
    .slice(lastTool + 1)
    .flatMap((s) => (s.kind === "text" ? [s.text] : []))
    .join("\n\n");
}

export function messagesFromTranscript(entries: { question: string; events: StreamEvent[] }[]): ChatMessage[] {
  return entries.flatMap((entry, index) => {
    const user: ChatMessage = { id: `t${index}-q`, role: "user", text: entry.question, steps: [], status: "done", warnings: [] };
    const assistant = entry.events.reduce(applyEvent, newAssistantMessage(`t${index}-a`));
    return [user, assistant.status === "streaming" ? { ...assistant, status: "done" as const } : assistant];
  });
}
