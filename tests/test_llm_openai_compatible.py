import openai
import pytest

from app.agent.llm import (
    LLMConfig, LLMError, Message, OpenAICompatibleProvider, TextDelta, ToolCall, ToolResultMessage, ToolUse, simplify_schema,
)
from app.agent.tools import tool_specs


class FakeChunk:
    def __init__(self, content=None, tool_calls=None, usage=None, choices=True):
        delta = type("Delta", (), {"content": content, "tool_calls": tool_calls})()
        self.choices = [type("Choice", (), {"delta": delta})()] if choices else []
        self.usage = usage


def tool_part(index, call_id=None, name=None, arguments=None, extra=None):
    function = type("Fn", (), {"name": name, "arguments": arguments})()
    model_extra = {"extra_content": extra} if extra else {}
    return type("Part", (), {"index": index, "id": call_id, "function": function, "model_extra": model_extra})()


class FakeClient:
    def __init__(self, chunks=None, error=None):
        self.chunks, self.error, self.calls = chunks or [], error, []
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return iter(self.chunks)


def provider(name, client):
    built = OpenAICompatibleProvider(LLMConfig(provider=name, api_key="key-1234567890"), 512)
    built.client = client
    return built


def run(built, tools=None):
    return list(built.stream("sys", [Message(role="user", text="q")], tools or []))


def test_defaults_per_provider():
    gemini = OpenAICompatibleProvider(LLMConfig(provider="gemini", api_key="key-1234567890"), 512)
    assert "generativelanguage.googleapis.com" in str(gemini.client.base_url) and gemini.model == "gemini-2.5-flash"
    assert OpenAICompatibleProvider(LLMConfig(provider="openai", api_key="key-1234567890"), 512).model == "gpt-4o-mini"


def test_message_conversion():
    converted = provider("openai", FakeClient()).convert("sys", [
        Message(role="user", text="q"),
        Message(role="assistant", text="", tool_calls=[ToolCall(id="a", name="execute_sql", input={"query": "SELECT 1"})]),
        Message(role="tool", tool_results=[ToolResultMessage(call_id="a", content="{}")]),
    ])
    assert converted[0] == {"role": "system", "content": "sys"}
    assert converted[2]["tool_calls"][0]["function"] == {"name": "execute_sql", "arguments": '{"query": "SELECT 1"}'}
    assert converted[3] == {"role": "tool", "tool_call_id": "a", "content": "{}"}


def test_stream_assembles_text_and_fragmented_tool_calls():
    chunks = [
        FakeChunk(content="Look"),
        FakeChunk(content="ing"),
        FakeChunk(tool_calls=[tool_part(0, "c1", "execute_sql", '{"query": "SEL')]),
        FakeChunk(tool_calls=[tool_part(0, None, None, 'ECT 1"}')]),
        FakeChunk(tool_calls=[tool_part(1, "c2", "get_schema", "{}")]),
        FakeChunk(choices=False, usage=type("U", (), {"prompt_tokens": 5, "completion_tokens": 2})()),
    ]
    client = FakeClient(chunks)
    items = run(provider("gemini", client), tool_specs())
    assert "".join(i.text for i in items if isinstance(i, TextDelta)) == "Looking"
    calls = [i.call for i in items if isinstance(i, ToolUse)]
    assert [(c.id, c.name, c.input) for c in calls] == [("c1", "execute_sql", {"query": "SELECT 1"}), ("c2", "get_schema", {})]
    sent = client.calls[0]
    assert sent["stream"] is True and sent["max_tokens"] == 512 and "stream_options" not in sent


def test_parallel_calls_sharing_index_zero_stay_separate():
    chunks = [
        FakeChunk(tool_calls=[tool_part(0, "x1", "get_schema", "{}")]),
        FakeChunk(tool_calls=[tool_part(0, "x2", "data_quality_check", '{"dataset": "orders"}')]),
    ]
    calls = [i.call for i in run(provider("gemini", FakeClient(chunks))) if isinstance(i, ToolUse)]
    assert [c.name for c in calls] == ["get_schema", "data_quality_check"]


def test_invalid_tool_json_and_missing_ids_do_not_crash():
    call = next(i.call for i in run(provider("openai", FakeClient([FakeChunk(tool_calls=[tool_part(0, None, "execute_sql", "{broken")])]))) if isinstance(i, ToolUse))
    assert call.input == {} and call.id == "call_0"


def test_openai_uses_completion_token_parameter_and_usage():
    client = FakeClient([FakeChunk(content="x")])
    run(provider("openai", client))
    assert client.calls[0]["max_completion_tokens"] == 512 and client.calls[0]["stream_options"] == {"include_usage": True}


def test_errors_are_translated_without_leaking_the_key():
    response = type("R", (), {"status_code": 401, "headers": {}, "request": None})()
    cases = [
        (openai.AuthenticationError("bad", response=response, body=None), "rejected"),
        (openai.APIConnectionError(request=None), "reach"),
    ]
    for error, fragment in cases:
        with pytest.raises(LLMError) as exc:
            run(provider("gemini", FakeClient(error=error)))
        assert fragment in exc.value.message and "key-1234567890" not in exc.value.message


def test_tool_schemas_are_simplified_for_gemini():
    schemas = [simplify_schema(s.input_schema) for s in tool_specs()]
    forbidden = {"anyOf", "default", "$ref", "$defs", "additionalProperties"}

    def keys_of(node):
        if isinstance(node, dict):
            return set(node) | set().union(*(keys_of(v) for v in node.values()), set())
        if isinstance(node, list):
            return set().union(*(keys_of(v) for v in node), set())
        return set()

    assert not forbidden & keys_of(schemas)
    for schema in schemas:
        assert set(schema.get("required", [])) <= set(schema["properties"])
    visual = next(s for s in schemas if "chart_type" in s["properties"])
    assert visual["properties"]["series"]["type"] == "string"


def test_gemini_tool_replies_carry_the_function_name_but_openai_ones_do_not():
    history = [
        Message(role="assistant", text="", tool_calls=[ToolCall(id="a", name="execute_sql", input={})]),
        Message(role="tool", tool_results=[ToolResultMessage(call_id="a", content="{}")]),
    ]
    gemini = provider("gemini", FakeClient()).convert("s", history)[-1]
    openai_reply = provider("openai", FakeClient()).convert("s", history)[-1]
    assert gemini["name"] == "execute_sql" and "name" not in openai_reply


def test_provider_specific_tool_call_data_is_captured_and_sent_back_unchanged():
    signature = {"google": {"thought_signature": "opaque-signature-value"}}
    chunks = [
        FakeChunk(tool_calls=[tool_part(0, "c1", "execute_sql", '{"query": "SELECT 1"}', extra=signature)]),
        FakeChunk(tool_calls=[tool_part(1, "c2", "get_schema", "{}")]),
    ]
    calls = [i.call for i in run(provider("gemini", FakeClient(chunks))) if isinstance(i, ToolUse)]
    assert calls[0].extra == signature and calls[1].extra is None
    converted = provider("gemini", FakeClient()).convert("s", [Message(role="assistant", text="", tool_calls=calls)])[-1]["tool_calls"]
    assert converted[0]["extra_content"] == signature and "extra_content" not in converted[1]
