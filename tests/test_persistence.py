import json
import time

from fastapi.testclient import TestClient

from app.data.datasets import DatasetStore
from app.main import create_app
from conftest import DATA_DIR
from fakes import ScriptedLLM, call, say


def start(settings, llm=None):
    return TestClient(create_app(settings, lambda s, o=None: llm or ScriptedLLM()))


def test_store_reopens_with_tables_and_relationships(settings, tmp_path):
    first = DatasetStore(tmp_path / "s", settings)
    first.add_csv("customers.csv", (DATA_DIR / "customers.csv").read_bytes())
    first.add_csv("orders.csv", (DATA_DIR / "orders.csv").read_bytes())
    first.con.close()
    second = DatasetStore(tmp_path / "s", settings)
    assert second.table_names() == {"customers", "orders"}
    assert second.get_profile("orders").rows > 7000
    assert second.query("SELECT count(*) FROM orders").rows[0][0] == second.get_profile("orders").rows
    assert any(r.left_table == "orders" and r.right_table == "customers" for r in second.relationships)
    second.close(delete=False)


def test_sessions_survive_a_server_restart(settings):
    llm = ScriptedLLM(
        call("set_context_filters", filters={"region": "Europe"}),
        call("execute_sql", "b", query="SELECT count(*) AS n FROM orders"),
        say("There are 7,044 orders."),
    )
    with start(settings, llm) as before:
        sid = before.post("/api/sessions").json()["session_id"]
        before.post(f"/api/sessions/{sid}/samples")
        before.put(f"/api/sessions/{sid}/llm", json={"provider": "gemini", "api_key": "AQ.secret-key-value"})
        before.post(f"/api/sessions/{sid}/chat", json={"message": "How many orders?"})
        before.app.state.sessions.save(before.app.state.sessions.get(sid))
        for session in before.app.state.sessions.sessions.values():
            session.store.con.close()

    with start(settings) as after:
        state = after.get(f"/api/sessions/{sid}").json()
        assert {d["profile"]["name"] for d in state["datasets"]} == {"customers", "orders", "products"}
        assert state["filters"] == {"region": "Europe"}
        assert state["llm"] is None
        assert after.get(f"/api/sessions/{sid}/datasets/orders/preview?limit=3").json()["row_count"] == 3
        transcript = after.get(f"/api/sessions/{sid}/transcript").json()
        assert transcript[0]["question"] == "How many orders?"
        assert [e["type"] for e in transcript[0]["events"]][-1] == "done"
        session = after.app.state.sessions.get(sid)
        assert session.history and session.records[0].tools == ["set_context_filters", "execute_sql"]


def test_api_keys_are_never_written_to_disk(settings):
    secret = "AQ.never-on-disk-12345"
    with start(settings) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        client.put(f"/api/sessions/{sid}/llm", json={"provider": "openai", "api_key": secret})
        client.app.state.sessions.save(client.app.state.sessions.get(sid))
        folder = client.app.state.sessions.root / sid
        text = "".join(p.read_text(errors="ignore") for p in folder.iterdir() if p.suffix == ".json")
        assert secret not in text and "openai" not in json.loads((folder / "session.json").read_text()).keys()
        client.app.state.sessions.get(sid).store.con.close()


def test_expired_sessions_are_removed_on_restart(settings):
    settings.session_ttl_minutes = 1
    with start(settings) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        folder = client.app.state.sessions.root / sid
        payload = json.loads((folder / "session.json").read_text())
        payload["saved_at"] = time.time() - 3600
        (folder / "session.json").write_text(json.dumps(payload))
        client.app.state.sessions.get(sid).store.con.close()
    with start(settings) as client:
        assert client.get(f"/api/sessions/{sid}").status_code == 404
        assert not folder.exists()


def test_corrupt_session_folders_do_not_stop_startup(settings):
    with start(settings) as client:
        bad = client.app.state.sessions.root / "broken"
        bad.mkdir()
        (bad / "session.json").write_text("{not json")
    with start(settings) as client:
        assert client.get("/api/health").status_code == 200


def test_reset_clears_the_saved_transcript(settings):
    with start(settings, ScriptedLLM(say("hi"))) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        client.post(f"/api/sessions/{sid}/samples")
        client.post(f"/api/sessions/{sid}/chat", json={"message": "hello"})
        assert len(client.get(f"/api/sessions/{sid}/transcript").json()) == 1
        client.post(f"/api/sessions/{sid}/reset")
        assert client.get(f"/api/sessions/{sid}/transcript").json() == []


def test_uploads_are_streamed_and_incoming_files_cleaned_up(settings):
    with start(settings) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        big = b"a\n" + b"1\n" * (3 * 1024 * 1024)
        body = client.post(f"/api/sessions/{sid}/datasets", files=[("files", ("big.csv", big, "text/csv"))]).json()
        assert "limit" in body["errors"][0]["message"]
        good = client.post(f"/api/sessions/{sid}/datasets", files=[("files", ("ok.csv", b"a,b\n1,2\n3,4\n", "text/csv"))]).json()
        assert good["datasets"]
        incoming = client.app.state.sessions.root / sid / "incoming"
        assert list(incoming.iterdir()) == []
