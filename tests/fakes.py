from collections.abc import Callable, Iterator

from app.agent.llm import LLMError, LLMProvider, Message, TextDelta, ToolCall, ToolSpec, ToolUse


def say(text: str) -> list:
    return [TextDelta(text=text)]


def call(name: str, call_id: str = "c1", **input) -> list:
    return [ToolUse(call=ToolCall(id=call_id, name=name, input=input))]


class ScriptedLLM(LLMProvider):
    def __init__(self, *turns: list | Callable[[list[Message]], list] | Exception):
        self.turns = list(turns)
        self.requests: list[tuple[str, list[Message]]] = []

    def stream(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> Iterator:
        self.requests.append((system, list(messages)))
        if not self.turns:
            raise AssertionError("ScriptedLLM ran out of scripted turns")
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        items = turn(messages) if callable(turn) else turn
        yield from items


def failing_llm(message: str = "The LLM provider is down.") -> ScriptedLLM:
    return ScriptedLLM(LLMError(message))
