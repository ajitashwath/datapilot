import time
from collections.abc import Iterator
from typing import Any, Literal

from pydantic import BaseModel

from app.config import Settings
from app.logging_setup import log_event


class LLMError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ToolCall(BaseModel):
    id: str
    name: str
    input: dict[str, Any]


class ToolResultMessage(BaseModel):
    call_id: str
    content: str


class Message(BaseModel):
    role: Literal["user", "assistant", "tool"]
    text: str = ""
    tool_calls: list[ToolCall] = []
    tool_results: list[ToolResultMessage] = []


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class TextDelta(BaseModel):
    text: str


class ToolUse(BaseModel):
    call: ToolCall


class LLMProvider:
    def stream(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> Iterator[TextDelta | ToolUse]:
        raise NotImplementedError


class AnthropicProvider(LLMProvider):
    def __init__(self, settings: Settings):
        if not settings.anthropic_api_key:
            raise LLMError("No LLM API key is configured. Set ANTHROPIC_API_KEY on the server and restart it.")
        import anthropic

        self.anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=90)
        self.model = settings.llm_model
        self.max_tokens = settings.llm_max_tokens

    def convert(self, messages: list[Message]) -> list[dict]:
        converted = []
        for m in messages:
            if m.role == "user":
                converted.append({"role": "user", "content": m.text})
            elif m.role == "assistant":
                blocks: list[dict] = [{"type": "text", "text": m.text}] if m.text.strip() else []
                blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in m.tool_calls]
                converted.append({"role": "assistant", "content": blocks})
            else:
                blocks = [{"type": "tool_result", "tool_use_id": r.call_id, "content": r.content} for r in m.tool_results]
                converted.append({"role": "user", "content": blocks})
        return converted

    def stream(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> Iterator[TextDelta | ToolUse]:
        started = time.perf_counter()
        api_tools = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]
        try:
            with self.client.messages.stream(
                model=self.model, max_tokens=self.max_tokens, system=system,
                messages=self.convert(messages), tools=api_tools,
            ) as stream:
                for text in stream.text_stream:
                    yield TextDelta(text=text)
                final = stream.get_final_message()
        except self.anthropic.AuthenticationError as exc:
            raise LLMError("The LLM API key was rejected. Check ANTHROPIC_API_KEY.") from exc
        except self.anthropic.RateLimitError as exc:
            raise LLMError("The LLM provider is rate limiting requests. Please try again in a moment.") from exc
        except self.anthropic.APIConnectionError as exc:
            raise LLMError("Could not reach the LLM provider. Check the network connection.") from exc
        except self.anthropic.APIError as exc:
            log_event("llm_api_error", error=str(exc)[:300])
            raise LLMError("The LLM provider returned an error. Please try again.") from exc
        log_event(
            "llm_request", model=self.model, duration_ms=round((time.perf_counter() - started) * 1000, 1),
            input_tokens=final.usage.input_tokens, output_tokens=final.usage.output_tokens, stop_reason=final.stop_reason,
        )
        for block in final.content:
            if block.type == "tool_use":
                yield ToolUse(call=ToolCall(id=block.id, name=block.name, input=block.input if isinstance(block.input, dict) else {}))


def create_provider(settings: Settings) -> LLMProvider:
    return AnthropicProvider(settings)
