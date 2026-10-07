import pytest
from fastapi.testclient import TestClient

from app.errors import UserError
from app.main import create_app
from app.secrets_box import SecretBox
from fakes import ScriptedLLM, say


def start(settings, llm=None):
    return TestClient(create_app(settings, lambda s, o=None: llm or ScriptedLLM(say("ok"), say("ok"), say("ok"), say("ok"))))


def test_auth_is_off_by_default(settings):
    with start(settings) as client:
        assert client.get("/api/config").json()["auth_required"] is False
        assert client.post("/api/sessions").status_code == 200


def test_access_token_protects_everything_except_health_and_config(settings):
    settings.access_token = "s3cret-token"
    with start(settings) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/config").json()["auth_required"] is True
        assert client.post("/api/sessions").status_code == 401
        assert client.get("/api/metrics").status_code == 401
        wrong = client.post("/api/sessions", headers={"Authorization": "Bearer nope"})
        assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "unauthorized"
        assert "s3cret-token" not in wrong.text
        ok = client.post("/api/sessions", headers={"Authorization": "Bearer s3cret-token"})
        assert ok.status_code == 200
        sid = ok.json()["session_id"]
        assert client.get(f"/api/sessions/{sid}").status_code == 401
        assert client.get(f"/api/sessions/{sid}", headers={"Authorization": "Bearer s3cret-token"}).status_code == 200


def test_chat_rate_limit_returns_429_with_retry_after(settings):
    settings.chat_per_minute = 2
    with start(settings) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        client.post(f"/api/sessions/{sid}/samples")
        statuses = [client.post(f"/api/sessions/{sid}/chat", json={"message": "hi"}).status_code for _ in range(3)]
        assert statuses == [200, 200, 429]
        limited = client.post(f"/api/sessions/{sid}/chat", json={"message": "hi"})
        assert limited.json()["error"]["code"] == "rate_limited" and int(limited.headers["retry-after"]) >= 1


def test_upload_and_session_creation_are_rate_limited(settings):
    settings.upload_per_minute = 1
    settings.session_create_per_hour = 2
    with start(settings) as client:
        first = client.post("/api/sessions").json()["session_id"]
        client.post("/api/sessions")
        assert client.post("/api/sessions").status_code == 429
        files = [("files", ("a.csv", b"a,b\n1,2\n3,4\n", "text/csv"))]
        assert client.post(f"/api/sessions/{first}/datasets", files=files).status_code == 200
        assert client.post(f"/api/sessions/{first}/datasets", files=files).status_code == 429


def test_rate_limits_are_per_client(settings):
    settings.chat_per_minute = 1
    settings.trust_proxy = True
    with start(settings) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        client.post(f"/api/sessions/{sid}/samples")
        body = {"message": "hi"}
        assert client.post(f"/api/sessions/{sid}/chat", json=body, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
        assert client.post(f"/api/sessions/{sid}/chat", json=body, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429
        assert client.post(f"/api/sessions/{sid}/chat", json=body, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200


def test_shared_key_quota_is_enforced_but_own_key_is_exempt(settings):
    settings.server_key_turn_limit = 1
    with start(settings) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        client.post(f"/api/sessions/{sid}/samples")
        assert client.post(f"/api/sessions/{sid}/chat", json={"message": "one"}).status_code == 200
        blocked = client.post(f"/api/sessions/{sid}/chat", json={"message": "two"})
        assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "quota_exceeded"
        client.put(f"/api/sessions/{sid}/llm", json={"provider": "gemini", "api_key": "AQ.my-own-key-123"})
        assert client.post(f"/api/sessions/{sid}/chat", json={"message": "three"}).status_code == 200


def test_secret_box_round_trip_and_wrong_key():
    box = SecretBox()
    blob = box.seal("AQ.plain-text-key")
    assert b"plain-text-key" not in blob and box.open(blob) == "AQ.plain-text-key"
    with pytest.raises(UserError):
        SecretBox().open(blob)


def test_metrics_endpoint_exposes_counters(settings):
    with start(settings) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        client.post(f"/api/sessions/{sid}/samples")
        client.post(f"/api/sessions/{sid}/chat", json={"message": "hi"})
        text = client.get("/api/metrics").text
        assert 'datapilot_http_requests_total{method="POST",path="/api/sessions",status="200"}' in text
        assert 'datapilot_chat_turns_total{outcome="ok"}' in text
        assert "datapilot_sessions_active 1.0" in text
