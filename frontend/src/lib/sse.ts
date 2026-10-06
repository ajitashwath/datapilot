import type { StreamEvent } from "./types";

export function parseSseChunk(buffer: string): { events: StreamEvent[]; rest: string } {
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: StreamEvent[] = [];
  for (const block of blocks) {
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data: "))
      .map((line) => line.slice(6))
      .join("\n");
    if (!data) continue;
    try {
      events.push(JSON.parse(data) as StreamEvent);
    } catch {
      continue;
    }
  }
  return { events, rest };
}
