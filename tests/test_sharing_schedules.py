import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from fakes import ScriptedLLM, say

PASSWORD = "correct horse battery"


@pytest.fixture
def quiet(settings):
    settings.scheduler_enabled = False
    settings.schedule_min_minutes = 1
    return settings


def start(settings, llm=None):
    return TestClient(create_app(settings, lambda s, o=None: llm or ScriptedLLM(say("Revenue grew."), say("Second answer."))))


def session_with_chat(client, headers=None):
    sid = client.post("/api/sessions", headers=headers).json()["session_id"]
    client.post(f"/api/sessions/{sid}/samples", headers=headers)
    client.post(f"/api/sessions/{sid}/chat", json={"message": "How is revenue?"}, headers=headers)
    return sid


def register(client, email):
    token = client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "name": email.split("@")[0]}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestSharing:
    def test_cannot_share_an_empty_conversation(self, quiet):
        with start(quiet) as client:
            sid = client.post("/api/sessions").json()["session_id"]
            assert client.post(f"/api/sessions/{sid}/shares", json={}).json()["error"]["code"] == "nothing_to_share"

    def test_public_link_serves_a_frozen_snapshot_without_credentials(self, quiet):
        quiet.access_token = "team-secret"
        owner = {"Authorization": "Bearer team-secret"}
        with start(quiet) as client:
            sid = session_with_chat(client, owner)
            share = client.post(f"/api/sessions/{sid}/shares", headers=owner, json={"title": "Q3 review"}).json()
            assert len(share["token"]) >= 20
            public = client.get(f"/api/shared/{share['token']}")
            assert public.status_code == 200
            assert public.headers["cache-control"] == "no-store" and "noindex" in public.headers["x-robots-tag"]
            body = public.json()
            assert body["title"] == "Q3 review" and body["transcript"][0]["question"] == "How is revenue?"
            assert {d["name"] for d in body["datasets"]} == {"customers", "orders", "products"}
            assert "llm" not in str(body).lower() or "api_key" not in str(body)
            client.post(f"/api/sessions/{sid}/chat", headers=owner, json={"message": "Another question"})
            assert len(client.get(f"/api/shared/{share['token']}").json()["transcript"]) == 1

    def test_revoked_and_unknown_links_return_404(self, quiet):
        with start(quiet) as client:
            sid = session_with_chat(client)
            token = client.post(f"/api/sessions/{sid}/shares", json={}).json()["token"]
            assert [s["token"] for s in client.get(f"/api/sessions/{sid}/shares").json()] == [token]
            assert client.delete(f"/api/sessions/{sid}/shares/{token}").status_code == 200
            assert client.get(f"/api/shared/{token}").status_code == 404
            assert client.get("/api/shared/not-a-real-token").status_code == 404
            assert client.delete(f"/api/sessions/{sid}/shares/not-a-real-token").status_code == 404

    def test_share_limit_and_public_rate_limit(self, quiet):
        quiet.max_shares_per_session = 2
        quiet.shared_per_minute = 3
        with start(quiet) as client:
            sid = session_with_chat(client)
            tokens = [client.post(f"/api/sessions/{sid}/shares", json={}) for _ in range(3)]
            assert [t.status_code for t in tokens] == [200, 200, 422]
            link = tokens[0].json()["token"]
            codes = [client.get(f"/api/shared/{link}").status_code for _ in range(5)]
            assert codes[-1] == 429 and codes[0] == 200

    def test_only_the_owner_can_manage_shares_in_accounts_mode(self, quiet):
        quiet.auth_mode = "accounts"
        with start(quiet) as client:
            ann, bob = register(client, "ann@example.com"), register(client, "bob@example.com")
            sid = session_with_chat(client, ann)
            team = client.post("/api/teams", headers=ann, json={"name": "T"}).json()
            client.post(f"/api/teams/{team['id']}/members", headers=ann, json={"email": "bob@example.com", "role": "member"})
            client.patch(f"/api/sessions/{sid}", headers=ann, json={"team_id": team["id"]})
            assert client.post(f"/api/sessions/{sid}/shares", headers=bob, json={}).status_code == 403
            assert client.get(f"/api/sessions/{sid}/shares", headers=bob).status_code == 403
            token = client.post(f"/api/sessions/{sid}/shares", headers=ann, json={}).json()["token"]
            assert client.get(f"/api/shared/{token}").status_code == 200


class TestSchedules:
    def make(self, client, **overrides):
        sid = client.post("/api/sessions").json()["session_id"]
        client.post(f"/api/sessions/{sid}/samples")
        body = {"name": "Revenue by region", "sql": 'SELECT region, sum(revenue) AS total FROM orders GROUP BY 1 ORDER BY 2 DESC', "every_minutes": 60, **overrides}
        return sid, client.post(f"/api/sessions/{sid}/schedules", json=body)

    def test_validation(self, quiet):
        quiet.schedule_min_minutes = 15
        with start(quiet) as client:
            sid, short = self.make(client, every_minutes=5)
            assert short.json()["error"]["code"] == "interval_too_short"
            assert self.make(client, every_minutes=60 * 24 * 40)[1].json()["error"]["code"] == "interval_too_long"
            base = {"name": "x", "every_minutes": 60}
            assert client.post(f"/api/sessions/{sid}/schedules", json={**base, "sql": "DROP TABLE orders"}).status_code == 400
            assert client.post(f"/api/sessions/{sid}/schedules", json={**base, "sql": "SELECT * FROM ghosts"}).status_code == 400
            assert client.post(f"/api/sessions/{sid}/schedules", json={**base, "sql": "SELECT * FROM read_csv('x.csv')"}).status_code == 400
            assert client.post(f"/api/sessions/{sid}/schedules", json={"name": "", "sql": "SELECT 1", "every_minutes": 60}).status_code == 422

    def test_run_now_stores_results_and_history_is_capped(self, quiet):
        quiet.schedule_runs_kept = 3
        with start(quiet) as client:
            sid, created = self.make(client)
            schedule = created.json()
            assert schedule["last_run"] is None and schedule["next_run_at"] > time.time()
            for _ in range(5):
                outcome = client.post(f"/api/sessions/{sid}/schedules/{schedule['id']}/run").json()
            assert outcome["run"]["ok"] and outcome["run"]["columns"] == ["region", "total"] and outcome["run"]["rows"][0][0] == "North America"
            assert len(client.get(f"/api/sessions/{sid}/schedules/{schedule['id']}/runs").json()) == 3
            listed = client.get(f"/api/sessions/{sid}/schedules").json()
            assert listed[0]["last_run"]["ok"] and listed[0]["last_run"]["row_count"] == 5

    def test_row_count_is_the_real_total_even_though_only_fifty_rows_are_stored(self, quiet):
        with start(quiet) as client:
            sid = client.post("/api/sessions").json()["session_id"]
            client.post(f"/api/sessions/{sid}/samples")
            body = {"name": "All orders", "sql": "SELECT * FROM orders", "every_minutes": 60}
            schedule_id = client.post(f"/api/sessions/{sid}/schedules", json=body).json()["id"]
            run = client.post(f"/api/sessions/{sid}/schedules/{schedule_id}/run").json()["run"]
            assert run["row_count"] == 7044
            assert len(run["rows"]) == 50

    def test_scheduler_runs_due_schedules_and_advances_them(self, quiet):
        with start(quiet) as client:
            sid, created = self.make(client, every_minutes=30)
            schedule_id = created.json()["id"]
            scheduler = client.app.state.scheduler
            assert scheduler.run_due(time.time()) == 0
            assert scheduler.run_due(time.time() + 31 * 60) == 1
            row = client.app.state.db.one("SELECT next_run_at FROM schedules WHERE id = ?", (schedule_id,))
            assert row["next_run_at"] > time.time() + 29 * 60
            assert len(client.get(f"/api/sessions/{sid}/schedules/{schedule_id}/runs").json()) == 1

    def test_failures_are_recorded_not_raised(self, quiet):
        with start(quiet) as client:
            sid, created = self.make(client)
            schedule_id = created.json()["id"]
            client.delete(f"/api/sessions/{sid}/datasets/orders")
            result = client.post(f"/api/sessions/{sid}/schedules/{schedule_id}/run").json()
            assert result["run"]["ok"] is False and "orders" in result["run"]["error"]
            assert client.get(f"/api/sessions/{sid}/schedules").json()[0]["last_run"]["ok"] is False

    def test_disable_delete_and_session_cleanup(self, quiet):
        with start(quiet) as client:
            sid, created = self.make(client, every_minutes=30)
            schedule_id = created.json()["id"]
            paused = client.patch(f"/api/sessions/{sid}/schedules/{schedule_id}", json={"enabled": False}).json()
            assert paused["enabled"] is False
            assert client.app.state.scheduler.run_due(time.time() + 3600 * 24) == 0
            client.post(f"/api/sessions/{sid}/schedules/{schedule_id}/run")
            assert client.delete(f"/api/sessions/{sid}/schedules/{schedule_id}").status_code == 200
            assert client.app.state.db.all("SELECT id FROM schedule_runs") == []
            assert client.get(f"/api/sessions/{sid}/schedules/{schedule_id}/runs").status_code == 404
            _, second = self.make(client)
            other = second.json()["id"]
            sid2 = client.app.state.db.one("SELECT session_id FROM schedules WHERE id = ?", (other,))["session_id"]
            client.delete(f"/api/sessions/{sid2}")
            assert client.app.state.db.all("SELECT id FROM schedules") == []

    def test_schedule_limit(self, quiet):
        quiet.max_schedules_per_session = 2
        with start(quiet) as client:
            sid, _ = self.make(client)
            client.post(f"/api/sessions/{sid}/schedules", json={"name": "b", "sql": "SELECT 1", "every_minutes": 60})
            third = client.post(f"/api/sessions/{sid}/schedules", json={"name": "c", "sql": "SELECT 1", "every_minutes": 60})
            assert third.json()["error"]["code"] == "too_many_schedules"

    def test_scheduled_sessions_do_not_expire_and_busy_ones_are_retried(self, quiet):
        quiet.session_ttl_minutes = 1
        with start(quiet) as client:
            sid, created = self.make(client, every_minutes=30)
            manager = client.app.state.sessions
            assert manager.expired(sid, time.time() - 3600) is False
            session = manager.get(sid)
            session.lock.acquire()
            try:
                assert client.app.state.scheduler.run_due(time.time() + 31 * 60) == 0
            finally:
                session.lock.release()
            retry_at = client.app.state.db.one("SELECT next_run_at FROM schedules WHERE id = ?", (created.json()["id"],))["next_run_at"]
            assert retry_at < time.time() + 120

    def test_read_only_members_can_view_but_not_change_schedules(self, quiet):
        quiet.auth_mode = "accounts"
        with start(quiet) as client:
            ann, bob = register(client, "ann@example.com"), register(client, "bob@example.com")
            sid = client.post("/api/sessions", headers=ann).json()["session_id"]
            client.post(f"/api/sessions/{sid}/samples", headers=ann)
            team = client.post("/api/teams", headers=ann, json={"name": "T"}).json()
            client.post(f"/api/teams/{team['id']}/members", headers=ann, json={"email": "bob@example.com", "role": "viewer"})
            client.patch(f"/api/sessions/{sid}", headers=ann, json={"team_id": team["id"]})
            body = {"name": "s", "sql": "SELECT 1", "every_minutes": 60}
            assert client.post(f"/api/sessions/{sid}/schedules", headers=bob, json=body).status_code == 403
            assert client.post(f"/api/sessions/{sid}/schedules", headers=ann, json=body).status_code == 200
            assert len(client.get(f"/api/sessions/{sid}/schedules", headers=bob).json()) == 1

    def test_scheduled_refresh_pulls_new_data_for_url_sources(self, quiet, monkeypatch):
        import socket

        monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))])
        content = {"csv": b"city,sales\nA,1\nB,2\nC,3\n"}
        with start(quiet) as client:
            client.app.state.http_transport = httpx.MockTransport(lambda request: httpx.Response(200, content=content["csv"]))
            client.app.state.scheduler.transport = client.app.state.http_transport
            sid = client.post("/api/sessions").json()["session_id"]
            job = client.post(f"/api/sessions/{sid}/connectors/url", json={"url": "https://data.example.com/sales.csv"}).json()["job_id"]
            for _ in range(100):
                if client.get(f"/api/jobs/{job}").json()["status"] in ("done", "error"):
                    break
                time.sleep(0.05)
            body = {"name": "total", "sql": "SELECT sum(sales) AS total FROM sales", "every_minutes": 30, "refresh_sources": True}
            schedule_id = client.post(f"/api/sessions/{sid}/schedules", json=body).json()["id"]
            content["csv"] = b"city,sales\nA,10\nB,20\nC,30\nD,40\n"
            assert client.app.state.scheduler.run_due(time.time() + 31 * 60) == 1
            run = client.get(f"/api/sessions/{sid}/schedules/{schedule_id}/runs").json()[0]
            assert run["ok"] and run["rows"] == [[100]] and "Refreshed sales" in run["note"]
