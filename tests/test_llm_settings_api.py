from fastapi.testclient import TestClient

from app.main import create_app
from fakes import ScriptedLLM, say

SECRET = "AQ.SuperSecretKeyValue123"


def test_session_key_is_stored_and_never_returned(settings):
    with TestClient(create_app(settings, lambda s, o=None: ScriptedLLM())) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        response = client.put(f"/api/sessions/{sid}/llm", json={"provider": "gemini", "api_key": SECRET})
        assert response.status_code == 200
        assert response.json()["llm"] == {"provider": "gemini", "model": "gemini-2.5-flash"}
        assert SECRET not in response.text and SECRET not in client.get(f"/api/sessions/{sid}").text
        manager = client.app.state.sessions
        sealed = manager.get(sid).llm
        assert SECRET.encode() not in sealed.blob
        assert manager.open_llm(sealed).api_key.get_secret_value() == SECRET
        assert client.delete(f"/api/sessions/{sid}/llm").json()["llm"] is None


def test_validation_rejects_bad_input_without_echoing_it(settings):
    with TestClient(create_app(settings, lambda s, o=None: ScriptedLLM())) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        url = f"/api/sessions/{sid}/llm"
        assert client.put(url, json={"provider": "gemini", "api_key": "short"}).status_code == 422
        assert client.put(url, json={"provider": "bogus", "api_key": "x" * 20}).status_code == 422
        bad_model = client.put(url, json={"provider": "openai", "api_key": "x" * 20, "model": "a b;rm"})
        assert bad_model.status_code == 422 and "x" * 20 not in bad_model.text


def test_chat_uses_the_session_key_and_provider(settings):
    seen = []

    def factory(s, override):
        seen.append(override)
        return ScriptedLLM(say("ok"))

    settings.anthropic_api_key = ""
    with TestClient(create_app(settings, factory)) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        client.post(f"/api/sessions/{sid}/samples")
        assert client.get("/api/config").json()["llm_configured"] is False
        client.put(f"/api/sessions/{sid}/llm", json={"provider": "openai", "api_key": "sk-test-key-123456", "model": "gpt-4o-mini"})
        client.post(f"/api/sessions/{sid}/chat", json={"message": "hi"})
    assert seen[0].provider == "openai" and seen[0].resolved_model() == "gpt-4o-mini"
