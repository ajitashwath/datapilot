import type { ReactNode } from "react";

const LIST_ITEM = /^\s*([-*]|\d+\.)\s+/;
const HEADING = /^#{1,4}\s/;

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="font-semibold text-slate-900">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={i} className="rounded bg-slate-100 px-1 py-0.5 text-[0.85em] text-brand-700">
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

function splitCells(line: string): string[] {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => cell.trim());
}

function renderTable(lines: string[], key: number): ReactNode {
  const [header, , ...body] = lines;
  return (
    <div key={key} tabIndex={0} role="region" aria-label="Table" className="my-2 overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            {splitCells(header).map((cell, i) => (
              <th key={i} className="px-3 py-1.5 font-medium">
                {inline(cell)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {body.map((line, r) => (
            <tr key={r}>
              {splitCells(line).map((cell, i) => (
                <td key={i} className="px-3 py-1.5">
                  {inline(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
    } else if (line.trim().startsWith("|") && lines[i + 1]?.includes("---")) {
      const start = i;
      while (i < lines.length && lines[i].trim().startsWith("|")) i++;
      blocks.push(renderTable(lines.slice(start, i), start));
    } else if (LIST_ITEM.test(line)) {
      const start = i;
      const ordered = /^\s*\d+\./.test(line);
      const items: string[] = [];
      while (i < lines.length && LIST_ITEM.test(lines[i])) items.push(lines[i++].replace(LIST_ITEM, ""));
      const List = ordered ? "ol" : "ul";
      blocks.push(
        <List key={start} className={`my-1.5 space-y-1 pl-5 ${ordered ? "list-decimal" : "list-disc"}`}>
          {items.map((item, n) => (
            <li key={n}>{inline(item)}</li>
          ))}
        </List>,
      );
    } else if (HEADING.test(line)) {
      blocks.push(
        <h4 key={i} className="mb-1 mt-3 font-semibold text-slate-900">
          {inline(line.replace(/^#+\s*/, ""))}
        </h4>,
      );
      i++;
    } else {
      const start = i;
      const paragraph: string[] = [];
      while (i < lines.length && lines[i].trim() && !LIST_ITEM.test(lines[i]) && !lines[i].trim().startsWith("|") && !HEADING.test(lines[i])) {
        paragraph.push(lines[i++]);
      }
      blocks.push(
        <p key={start} className="my-1.5 leading-relaxed">
          {inline(paragraph.join(" "))}
        </p>,
      );
    }
  }
  return <div className="text-[15px] text-slate-700">{blocks}</div>;
}
