import hashlib
import hmac
import json
import socket

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from fakes import ScriptedLLM

HOOK = "https://hooks.example.com/services/T000/B000/secrettoken"


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))])


@pytest.fixture
def client(settings, public_dns):
    settings.scheduler_enabled = False
    settings.schedule_min_minutes = 1
    with TestClient(create_app(settings, lambda s, o=None: ScriptedLLM())) as c:
        yield c


def workspace(client):
    sid = client.post("/api/sessions").json()["session_id"]
    client.post(f"/api/sessions/{sid}/samples")
    return sid


def make(client, sid, **extra):
    body = {"name": "Revenue check", "sql": "SELECT region, sum(revenue) AS total FROM orders GROUP BY 1", "every_minutes": 60, **extra}
    return client.post(f"/api/sessions/{sid}/schedules", json=body)


def collect(client, status=200):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status)

    client.app.state.http_transport = httpx.MockTransport(handler)
    return seen


def run(client, sid, schedule_id):
    return client.post(f"/api/sessions/{sid}/schedules/{schedule_id}/run").json()


class TestWebhooks:
    def test_a_signed_summary_is_posted_without_any_data(self, client):
        sid = workspace(client)
        created = make(client, sid, notify="always", webhook_url=HOOK).json()
        seen = collect(client)
        result = run(client, sid, created["id"])
        assert len(seen) == 1
        request = seen[0]
        payload = json.loads(request.content)
        assert payload["event"] == "schedule.run" and payload["ok"] is True and payload["row_count"] == 5 and payload["schedule"] == "Revenue check"
        assert "North America" not in request.content.decode() and "total" not in payload
        expected = hmac.new(created["webhook_secret"].encode(), request.content, hashlib.sha256).hexdigest()
        assert request.headers["X-DataPilot-Signature"] == f"sha256={expected}"
        assert request.headers["Host"] == "hooks.example.com" and request.url.host == "93.184.216.34"
        assert "Webhook delivered" in result["run"]["note"]

    def test_the_secret_is_shown_once_and_the_url_is_never_echoed(self, client):
        sid = workspace(client)
        created = make(client, sid, notify="always", webhook_url=HOOK).json()
        assert created["webhook_secret"] and created["webhook_host"] == "hooks.example.com"
        listed = client.get(f"/api/sessions/{sid}/schedules").json()[0]
        assert "webhook_secret" not in listed and "secrettoken" not in json.dumps(listed)

    def test_failure_mode_only_calls_when_a_run_fails(self, client):
        sid = workspace(client)
        created = make(client, sid, notify="failure", webhook_url=HOOK).json()
        seen = collect(client)
        run(client, sid, created["id"])
        assert seen == []
        client.delete(f"/api/sessions/{sid}/datasets/orders")
        result = run(client, sid, created["id"])
        assert len(seen) == 1 and json.loads(seen[0].content)["ok"] is False
        assert "orders" in json.loads(seen[0].content)["error"] and result["run"]["ok"] is False

    def test_receiver_errors_are_recorded_and_do_not_break_the_run(self, client):
        sid = workspace(client)
        created = make(client, sid, notify="always", webhook_url=HOOK).json()
        collect(client, status=500)
        result = run(client, sid, created["id"])
        assert result["run"]["ok"] is True and "failed with status 500" in result["run"]["note"]

    def test_unreachable_receivers_are_recorded(self, client):
        sid = workspace(client)
        created = make(client, sid, notify="always", webhook_url=HOOK).json()

        def refuse(request):
            raise httpx.ConnectError("refused")

        client.app.state.http_transport = httpx.MockTransport(refuse)
        result = run(client, sid, created["id"])
        assert result["run"]["ok"] is True and "could not be reached" in result["run"]["note"]

    def test_redirects_are_not_followed(self, client):
        sid = workspace(client)
        created = make(client, sid, notify="always", webhook_url=HOOK).json()
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})

        client.app.state.http_transport = httpx.MockTransport(handler)
        result = run(client, sid, created["id"])
        assert len(seen) == 1 and "status 302" in result["run"]["note"]


class TestWebhookValidation:
    @pytest.mark.parametrize("url", ["http://hooks.example.com/x", "https://user:pw@hooks.example.com/x", "ftp://hooks.example.com/x", "not a url"])
    def test_only_plain_https_addresses_are_accepted(self, client, url):
        assert make(client, workspace(client), notify="always", webhook_url=url).status_code == 422

    def test_private_addresses_are_refused(self, client, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))])
        response = make(client, workspace(client), notify="always", webhook_url=HOOK)
        assert response.status_code == 422 and response.json()["error"]["code"] == "blocked_address"

    def test_an_address_needs_a_notify_mode(self, client):
        response = make(client, workspace(client), notify="none", webhook_url=HOOK)
        assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_notify"

    def test_hosts_that_turn_private_after_creation_are_blocked_at_send_time(self, client, monkeypatch):
        sid = workspace(client)
        created = make(client, sid, notify="always", webhook_url=HOOK).json()
        seen = collect(client)
        monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))])
        result = run(client, sid, created["id"])
        assert seen == [] and "Webhook not sent" in result["run"]["note"]

    def test_no_webhook_means_no_secret_and_no_call(self, client):
        sid = workspace(client)
        created = make(client, sid).json()
        seen = collect(client)
        run(client, sid, created["id"])
        assert "webhook_secret" not in created and created["webhook_host"] is None and seen == []
