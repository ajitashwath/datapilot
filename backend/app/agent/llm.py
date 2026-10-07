import json
import time
from collections.abc import Iterator
from typing import Any, Literal

from pydantic import BaseModel, SecretStr

from app.config import Settings
from app.logging_setup import log_event
from app.metrics import metrics

PROVIDER_DEFAULTS = {
    "anthropic": {"label": "Anthropic", "model": "claude-sonnet-5-5", "base_url": None},
    "gemini": {"label": "Gemini", "model": "gemini-2.5-flash", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/"},
    "openai": {"label": "OpenAI", "model": "gpt-4o-mini", "base_url": None},
}


class LLMError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class LLMConfig(BaseModel):
    provider: Literal["anthropic", "gemini", "openai"]
    api_key: SecretStr
    model: str = ""

    def resolved_model(self) -> str:
        return self.model or PROVIDER_DEFAULTS[self.provider]["model"]


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
    def __init__(self, config: LLMConfig, max_tokens: int):
        import anthropic

        self.anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=config.api_key.get_secret_value(), max_retries=2, timeout=90)
        self.model = config.resolved_model()
        self.max_tokens = max_tokens

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
            raise LLMError("The LLM API key was rejected. Check the key in Settings.") from exc
        except self.anthropic.RateLimitError as exc:
            raise LLMError("The LLM provider is rate limiting requests. Please try again in a moment.") from exc
        except self.anthropic.APIConnectionError as exc:
            raise LLMError("Could not reach the LLM provider. Check the network connection.") from exc
        except self.anthropic.APIError as exc:
            log_event("llm_api_error", provider="anthropic", error=str(exc)[:300])
            raise LLMError("The LLM provider returned an error. Please try again.") from exc
        elapsed = time.perf_counter() - started
        metrics.inc("datapilot_llm_requests_total", provider="anthropic")
        metrics.inc("datapilot_llm_seconds_sum", elapsed, provider="anthropic")
        log_event(
            "llm_request", provider="anthropic", model=self.model, duration_ms=round((time.perf_counter() - started) * 1000, 1),
            input_tokens=final.usage.input_tokens, output_tokens=final.usage.output_tokens, stop_reason=final.stop_reason,
        )
        for block in final.content:
            if block.type == "tool_use":
                yield ToolUse(call=ToolCall(id=block.id, name=block.name, input=block.input if isinstance(block.input, dict) else {}))


def simplify_schema(schema: Any) -> Any:
    if isinstance(schema, list):
        return [simplify_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    options = schema.get("anyOf")
    if options:
        concrete = [o for o in options if o.get("type") != "null"]
        if len(concrete) == 1:
            merged = {**{k: v for k, v in schema.items() if k != "anyOf"}, **concrete[0]}
            return simplify_schema(merged)
    cleaned = {}
    for key, value in schema.items():
        if key in ("title", "default", "additionalProperties"):
            continue
        if key == "properties" and isinstance(value, dict):
            cleaned[key] = {name: simplify_schema(sub) for name, sub in value.items()}
        else:
            cleaned[key] = simplify_schema(value)
    return cleaned


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, config: LLMConfig, max_tokens: int):
        import openai

        defaults = PROVIDER_DEFAULTS[config.provider]
        self.openai = openai
        self.provider = config.provider
        self.label = defaults["label"]
        self.client = openai.OpenAI(api_key=config.api_key.get_secret_value(), base_url=defaults["base_url"], max_retries=4, timeout=90)
        self.model = config.resolved_model()
        self.max_tokens = max_tokens

    def convert(self, system: str, messages: list[Message]) -> list[dict]:
        converted: list[dict] = [{"role": "system", "content": system}]
        for m in messages:
            if m.role == "user":
                converted.append({"role": "user", "content": m.text})
            elif m.role == "assistant":
                entry: dict = {"role": "assistant", "content": m.text or None}
                if m.tool_calls:
                    entry["tool_calls"] = [
                        {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.input)}}
                        for c in m.tool_calls
                    ]
                converted.append(entry)
            else:
                converted += [{"role": "tool", "tool_call_id": r.call_id, "content": r.content} for r in m.tool_results]
        return converted

    def request_options(self) -> dict:
        if self.provider == "openai":
            return {"max_completion_tokens": self.max_tokens, "stream_options": {"include_usage": True}}
        return {"max_tokens": self.max_tokens}

    def translate_error(self, exc: Exception) -> LLMError:
        openai = self.openai
        if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
            return LLMError(f"The {self.label} API key was rejected. Check the key in Settings.")
        if isinstance(exc, openai.RateLimitError):
            return LLMError(f"{self.label} is rate limiting requests or the quota is used up. Try again later.")
        if isinstance(exc, openai.NotFoundError):
            return LLMError(f"The model '{self.model}' was not found on {self.label}. Change the model in Settings.")
        if isinstance(exc, openai.APIConnectionError):
            return LLMError(f"Could not reach {self.label}. Check the network connection.")
        log_event("llm_api_error", provider=self.provider, error=str(exc)[:300])
        return LLMError(f"{self.label} returned an error. Please try again or choose another model.")

    def stream(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> Iterator[TextDelta | ToolUse]:
        started = time.perf_counter()
        api_tools = [
            {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": simplify_schema(t.input_schema)}}
            for t in tools
        ]
        slots: list[dict] = []
        by_index: dict[int, dict] = {}
        usage = None
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=self.convert(system, messages), tools=api_tools, stream=True, **self.request_options()
            )
            for chunk in response:
                usage = getattr(chunk, "usage", None) or usage
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    yield TextDelta(text=delta.content)
                for part in delta.tool_calls or []:
                    index = part.index or 0
                    slot = by_index.get(index)
                    if slot is None or (part.id and slot["id"] and part.id != slot["id"]):
                        slot = {"id": "", "name": "", "arguments": ""}
                        slots.append(slot)
                        by_index[index] = slot
                    slot["id"] = part.id or slot["id"]
                    if part.function:
                        slot["name"] += part.function.name or ""
                        slot["arguments"] += part.function.arguments or ""
        except self.openai.OpenAIError as exc:
            raise self.translate_error(exc) from exc
        elapsed = time.perf_counter() - started
        metrics.inc("datapilot_llm_requests_total", provider=self.provider)
        metrics.inc("datapilot_llm_seconds_sum", elapsed, provider=self.provider)
        log_event(
            "llm_request", provider=self.provider, model=self.model, duration_ms=round((time.perf_counter() - started) * 1000, 1),
            input_tokens=getattr(usage, "prompt_tokens", None), output_tokens=getattr(usage, "completion_tokens", None),
        )
        for n, slot in enumerate(slots):
            try:
                arguments = json.loads(slot["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments = {}
            yield ToolUse(call=ToolCall(id=slot["id"] or f"call_{n}", name=slot["name"], input=arguments if isinstance(arguments, dict) else {}))


def server_config(settings: Settings) -> LLMConfig | None:
    keys = {"anthropic": settings.anthropic_api_key, "gemini": settings.gemini_api_key, "openai": settings.openai_api_key}
    key = keys.get(settings.llm_provider, "")
    if not key:
        return None
    return LLMConfig(provider=settings.llm_provider, api_key=key, model=settings.llm_model)


def create_provider(settings: Settings, override: LLMConfig | None = None) -> LLMProvider:
    config = override or server_config(settings)
    if config is None:
        raise LLMError("No LLM API key is configured. Open Settings and add a Gemini or OpenAI API key.")
    provider_class = AnthropicProvider if config.provider == "anthropic" else OpenAICompatibleProvider
    return provider_class(config, settings.llm_max_tokens)
