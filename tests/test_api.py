import io
import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.agent.llm import create_provider
from app.logging_setup import JsonFormatter, logger
from app.main import create_app
from conftest import DATA_DIR
from fakes import ScriptedLLM, call, say


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        data = [line[6:] for line in block.splitlines() if line.startswith("data: ")]
        if data:
            events.append(json.loads(data[0]))
    return events


def upload(client, session_id, *names):
    files = [("files", (f"{n}.csv", (DATA_DIR / f"{n}.csv").read_bytes(), "text/csv")) for n in names]
    return client.post(f"/api/sessions/{session_id}/datasets", files=files)


@pytest.fixture
def llm():
    return ScriptedLLM()


@pytest.fixture
def client(settings, llm):
    with TestClient(create_app(settings, lambda s: llm), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def sid(client):
    return client.post("/api/sessions").json()["session_id"]


def test_health_and_config(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    config = client.get("/api/config").json()
    assert config["llm_configured"] and set(config["sample_datasets"]) == {"customers.csv", "orders.csv", "products.csv"}
    assert "test-key" not in json.dumps(config)


def test_upload_multiple_files_returns_profiles_and_quality(client, sid):
    body = upload(client, sid, "customers", "orders", "products").json()
    assert body["errors"] == [] and [d["profile"]["name"] for d in body["datasets"]] == ["customers", "orders", "products"]
    orders = body["datasets"][1]
    assert orders["profile"]["rows"] > 7000 and orders["issue_count"] > 0 and 0 < orders["quality_score"] < 100
    state = client.get(f"/api/sessions/{sid}").json()
    assert len(state["datasets"]) == 3 and len(state["relationships"]) == 2


def test_upload_reports_errors_per_file_without_failing_the_batch(client, sid):
    files = [
        ("files", ("good.csv", b"a,b\n1,2\n3,4\n", "text/csv")),
        ("files", ("sheet.xlsx", b"PK\x03\x04", "application/zip")),
        ("files", ("empty.csv", b"", "text/csv")),
        ("files", ("big.csv", b"a\n" * (3 * 1024 * 1024), "text/csv")),
    ]
    body = client.post(f"/api/sessions/{sid}/datasets", files=files).json()
    assert [d["profile"]["name"] for d in body["datasets"]] == ["good"]
    messages = {e["filename"]: e["message"] for e in body["errors"]}
    assert "not supported" in messages["sheet.xlsx"]
    assert "empty" in messages["empty.csv"]
    assert "limit" in messages["big.csv"]


def test_load_samples(client, sid):
    body = client.post(f"/api/sessions/{sid}/samples").json()
    assert len(body["datasets"]) == 3
    assert client.post(f"/api/sessions/{sid}/samples").json()["datasets"] == []


def test_preview_quality_summary_and_delete(client, sid):
    upload(client, sid, "orders")
    preview = client.get(f"/api/sessions/{sid}/datasets/orders/preview?limit=5").json()
    assert preview["row_count"] == 5 and "revenue" in preview["columns"]
    quality = client.get(f"/api/sessions/{sid}/datasets/orders/quality").json()
    assert any(i["type"] == "duplicate_rows" for i in quality["issues"])
    summary = client.get(f"/api/sessions/{sid}/datasets/orders/summary").json()
    assert summary["rows"] > 7000 and summary["suggested_questions"] and summary["distributions"]
    state = client.delete(f"/api/sessions/{sid}/datasets/orders").json()
    assert state["datasets"] == []


def test_unknown_session_and_dataset_give_404_without_stack_traces(client, sid):
    response = client.get("/api/sessions/nope")
    assert response.status_code == 404 and response.json()["error"]["code"] == "session_not_found"
    response = client.get(f"/api/sessions/{sid}/datasets/ghost/preview")
    assert response.status_code == 404 and "Traceback" not in response.text


def test_request_validation_errors_are_friendly(client, sid):
    response = client.post(f"/api/sessions/{sid}/chat", json={"message": ""})
    assert response.status_code == 422 and "message" in response.json()["error"]["message"]
    assert client.post(f"/api/sessions/{sid}/chat", json={"message": "x" * 5000}).status_code == 422


def test_chat_streams_events_in_order(client, sid, llm):
    upload(client, sid, "orders")
    llm.turns = [
        say("Checking. ") + call("execute_sql", query="SELECT count(*) AS n FROM orders"),
        say("There are 7,056 rows."),
    ]
    response = client.post(f"/api/sessions/{sid}/chat", json={"message": "How many rows?", "dataset": "orders"})
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    kinds = [e["type"] for e in events]
    assert kinds[0] == "text" and kinds.index("tool_call") < kinds.index("tool_result") < kinds.index("done")
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["result"]["sql"] == "SELECT count(*) AS n FROM orders" and result["result"]["table"]["rows"][0][0] > 7000
    assert client.get(f"/api/sessions/{sid}").json()["active_dataset"] == "orders"


def test_chat_without_dataset_asks_for_upload(client, sid):
    events = parse_sse(client.post(f"/api/sessions/{sid}/chat", json={"message": "hello"}).text)
    assert events[0]["type"] == "error" and "Upload" in events[0]["message"]


def test_chat_llm_failure_becomes_error_event(settings):
    app = create_app(settings, create_provider)
    app.state.settings.anthropic_api_key = ""
    with TestClient(app) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        upload(client, sid, "orders")
        events = parse_sse(client.post(f"/api/sessions/{sid}/chat", json={"message": "hi"}).text)
        assert events[-1]["type"] == "error" and "API key" in events[-1]["message"]


def test_chat_unexpected_failure_is_sanitised(client, sid, llm):
    upload(client, sid, "orders")

    class Exploding(ScriptedLLM):
        def stream(self, *args, **kwargs):
            raise RuntimeError("secret stack detail")
            yield

    client.app.state.llm_factory = lambda s: Exploding()
    events = parse_sse(client.post(f"/api/sessions/{sid}/chat", json={"message": "hi"}).text)
    assert events[-1]["type"] == "error" and "secret" not in events[-1]["message"]


def test_user_declared_relationship_and_filters(client, sid, llm):
    upload(client, sid, "orders", "customers")
    body = {"left_table": "orders", "left_column": "region", "right_table": "customers", "right_column": "region"}
    created = client.post(f"/api/sessions/{sid}/relationships", json=body).json()
    assert created["source"] == "user"
    bad = client.post(f"/api/sessions/{sid}/relationships", json={**body, "left_column": "nope"})
    assert bad.status_code == 404
    llm.turns = [call("set_context_filters", filters={"region": "Europe"}), say("Noted.")]
    client.post(f"/api/sessions/{sid}/chat", json={"message": "focus on Europe"})
    assert client.get(f"/api/sessions/{sid}").json()["filters"] == {"region": "Europe"}
    assert client.delete(f"/api/sessions/{sid}/filters").json()["filters"] == {}


def test_reset_clears_conversation(client, sid, llm):
    upload(client, sid, "orders")
    llm.turns = [say("hi")]
    client.post(f"/api/sessions/{sid}/chat", json={"message": "hello"})
    client.post(f"/api/sessions/{sid}/reset")
    session = client.app.state.sessions.get(sid)
    assert session.history == [] and session.records == []


def test_delete_session(client, sid):
    assert client.delete(f"/api/sessions/{sid}").json() == {"deleted": True}
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_request_id_header_and_structured_logs(client):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    try:
        response = client.get("/api/health", headers={"x-request-id": "abc123"})
    finally:
        logger.removeHandler(handler)
    assert response.headers["x-request-id"] == "abc123"
    logged = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert any(entry["event"] == "request" and entry["request_id"] == "abc123" for entry in logged)
