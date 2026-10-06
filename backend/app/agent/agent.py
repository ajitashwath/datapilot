import re
import time
from collections.abc import Iterator
from typing import Literal

from pydantic import BaseModel

from app.agent.llm import LLMError, LLMProvider, Message, TextDelta, ToolResultMessage
from app.agent.prompts import build_system_prompt
from app.agent.tools import result_for_llm, run_tool, tool_specs
from app.models import ToolResult
from app.session import AnalysisRecord, Session

HISTORY_RESULT_CHARS = 1500
NUMBER_PATTERN = re.compile(r"(?<![\w.])(\d+(?:,\d{3})*(?:\.\d+)?)(\s?(?:[kKmMbB]\b|thousand|million|billion))?")
SCALES = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}


class TextEvent(BaseModel):
    type: Literal["text"] = "text"
    step: int
    delta: str


class ToolCallEvent(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    step: int
    id: str
    name: str
    input: dict


class ToolResultEvent(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    step: int
    id: str
    name: str
    duration_ms: float
    result: ToolResult


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    tools_used: list[str]
    warnings: list[str]
    duration_ms: float


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


Event = TextEvent | ToolCallEvent | ToolResultEvent | DoneEvent | ErrorEvent


def number_from_match(match: re.Match) -> tuple[float, float]:
    raw = match.group(1).replace(",", "")
    suffix = (match.group(2) or "").strip().lower()
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    scale = SCALES.get(suffix, 1.0)
    return float(raw) * scale, 0.5 * 10 ** -decimals * scale + 1e-9


def parse_numbers(text: str) -> list[tuple[float, float]]:
    return [number_from_match(m) for m in NUMBER_PATTERN.finditer(text)]


def find_ungrounded_numbers(answer: str, tool_texts: list[str], question: str) -> list[str]:
    known = [value for text in tool_texts for value, _ in parse_numbers(text)]
    asked = {value for value, _ in parse_numbers(question)}
    missing = []
    for match in NUMBER_PATTERN.finditer(answer):
        value, tolerance = number_from_match(match)
        raw = match.group(1)
        is_year = "," not in raw and "." not in raw and 1900 <= value <= 2100
        if value <= 10 or is_year or value in asked:
            continue
        if not any(abs(value - k) <= max(tolerance, abs(k) * 1e-9) for k in known):
            missing.append(match.group(0).strip())
    return list(dict.fromkeys(missing))[:6]


def trim_history(history: list[Message], turns: int) -> list[Message]:
    starts = [i for i, m in enumerate(history) if m.role == "user"]
    if len(starts) <= turns:
        return history
    return history[starts[-turns]:]


def compact_for_history(messages: list[Message]) -> list[Message]:
    compacted = []
    for m in messages:
        if m.role == "tool":
            results = [ToolResultMessage(call_id=r.call_id, content=r.content[:HISTORY_RESULT_CHARS]) for r in m.tool_results]
            compacted.append(Message(role="tool", tool_results=results))
        else:
            compacted.append(m)
    return compacted


def preview_of(result: ToolResult) -> str:
    if result.table and result.table.rows:
        rows = result.table.rows[:3]
        return f"columns {result.table.columns}, first rows {rows}"
    if result.anomalies:
        return "; ".join(a.reason[:160] for a in result.anomalies[:2])
    return ""


def run_turn(session: Session, question: str, llm: LLMProvider) -> Iterator[Event]:
    settings = session.store.settings
    started = time.perf_counter()
    user_message = Message(role="user", text=question)
    messages = trim_history(session.history, settings.history_turns) + [user_message]
    new_messages = [user_message]
    system = build_system_prompt(session)
    specs = tool_specs()
    tools_used: list[str] = []
    tool_texts: list[str] = []
    preview = ""
    final_text = ""

    for step in range(settings.max_agent_steps):
        text, calls = "", []
        try:
            for item in llm.stream(system, messages, specs):
                if isinstance(item, TextDelta):
                    text += item.text
                    yield TextEvent(step=step, delta=item.text)
                else:
                    calls.append(item.call)
        except LLMError as exc:
            yield ErrorEvent(message=exc.message)
            return
        if not text.strip() and not calls:
            text = "I could not produce an answer for that. Please try rephrasing the question."
            yield TextEvent(step=step, delta=text)
        assistant = Message(role="assistant", text=text, tool_calls=calls)
        messages.append(assistant)
        new_messages.append(assistant)
        if not calls:
            final_text = text
            break
        results = []
        for call in calls:
            yield ToolCallEvent(step=step, id=call.id, name=call.name, input=call.input)
            tool_started = time.perf_counter()
            result = run_tool(session, call.name, call.input)
            llm_text = result_for_llm(result)
            tools_used.append(call.name)
            tool_texts.append(llm_text)
            preview = preview_of(result) or preview
            yield ToolResultEvent(
                step=step, id=call.id, name=call.name, result=result,
                duration_ms=round((time.perf_counter() - tool_started) * 1000, 1),
            )
            results.append(ToolResultMessage(call_id=call.id, content=llm_text))
        tool_message = Message(role="tool", tool_results=results)
        messages.append(tool_message)
        new_messages.append(tool_message)
    else:
        final_text = "I reached the maximum number of analysis steps for one question. Try asking a narrower question."
        yield TextEvent(step=settings.max_agent_steps, delta=final_text)
        new_messages.append(Message(role="assistant", text=final_text))

    warnings = []
    ungrounded = find_ungrounded_numbers(final_text, tool_texts, question)
    if ungrounded:
        warnings.append(f"These figures were not found in any tool result, please verify them: {', '.join(ungrounded)}.")
    session.history = trim_history(session.history + compact_for_history(new_messages), settings.history_turns)
    session.records.append(AnalysisRecord(
        question=question, answer=final_text, tools=list(dict.fromkeys(tools_used)), result_preview=preview,
    ))
    yield DoneEvent(
        tools_used=tools_used, warnings=warnings, duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
