import pytest
from fastapi.testclient import TestClient

from app.accounts import hash_password, verify_password
from app.main import create_app
from fakes import ScriptedLLM

PASSWORD = "correct horse battery"


@pytest.fixture
def accounts_settings(settings):
    settings.auth_mode = "accounts"
    settings.session_ttl_minutes = 1
    return settings


def start(settings):
    return TestClient(create_app(settings, lambda s, o=None: ScriptedLLM()))


def register(client, email, name="Test User", password=PASSWORD):
    response = client.post("/api/auth/register", json={"email": email, "password": password, "name": name})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}, response.json()["user"]


def new_session(client, headers):
    return client.post("/api/sessions", headers=headers).json()["session_id"]


def upload_small(client, headers, sid):
    files = [("files", ("a.csv", b"a,b\n1,2\n3,4\n5,6\n", "text/csv"))]
    return client.post(f"/api/sessions/{sid}/datasets", files=files, headers=headers)


def test_passwords_are_hashed_with_scrypt_and_verified():
    stored = hash_password("a long enough password")
    assert stored.startswith("scrypt$") and "a long enough password" not in stored
    assert verify_password("a long enough password", stored)
    assert not verify_password("wrong password!!", stored)
    assert not verify_password("anything", "garbage")


def test_registration_validation(accounts_settings):
    with start(accounts_settings) as client:
        post = lambda **body: client.post("/api/auth/register", json={"email": "a@b.co", "password": PASSWORD, "name": "A", **body})
        assert post(email="not-an-email").json()["error"]["code"] == "invalid_email"
        assert post(password="short").json()["error"]["code"] == "weak_password"
        assert post(name="  ").json()["error"]["code"] == "invalid_name"
        assert post().status_code == 200
        assert post().json()["error"]["code"] == "email_taken"
        assert post(email="A@B.CO").status_code == 409


def test_registration_can_be_closed_or_domain_restricted(accounts_settings):
    accounts_settings.registration = "closed"
    with start(accounts_settings) as client:
        assert client.post("/api/auth/register", json={"email": "a@b.co", "password": PASSWORD, "name": "A"}).status_code == 403
    accounts_settings.registration = "open"
    accounts_settings.allowed_email_domain = "corp.example"
    with start(accounts_settings) as client:
        other = client.post("/api/auth/register", json={"email": "a@gmail.com", "password": PASSWORD, "name": "A"})
        assert other.json()["error"]["code"] == "email_domain_not_allowed"
        assert client.post("/api/auth/register", json={"email": "a@corp.example", "password": PASSWORD, "name": "A"}).status_code == 200


def test_login_logout_and_token_hygiene(accounts_settings):
    with start(accounts_settings) as client:
        headers, user = register(client, "ann@example.com")
        assert client.get("/api/auth/me", headers=headers).json()["email"] == "ann@example.com"
        assert client.get("/api/auth/me").status_code == 401
        assert client.get("/api/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401
        bad = client.post("/api/auth/login", json={"email": "ann@example.com", "password": "wrong password!!"})
        unknown = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "wrong password!!"})
        assert bad.status_code == unknown.status_code == 401 and bad.json() == unknown.json()
        login = client.post("/api/auth/login", json={"email": "ann@example.com", "password": PASSWORD}).json()
        stored = client.app.state.db.all("SELECT token_hash FROM auth_tokens")
        assert login["token"] not in str(stored) and len(stored) == 2
        assert client.post("/api/auth/logout", headers=headers).json() == {"signed_out": True}
        assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_login_attempts_are_throttled(accounts_settings):
    accounts_settings.login_per_minute = 3
    with start(accounts_settings) as client:
        register(client, "ann@example.com")
        codes = [client.post("/api/auth/login", json={"email": "ann@example.com", "password": "wrong password!!"}).status_code for _ in range(5)]
        assert codes[-1] == 429 and 401 in codes


def test_accounts_endpoints_are_hidden_when_accounts_are_off(settings):
    with start(settings) as client:
        assert client.post("/api/auth/register", json={"email": "a@b.co", "password": PASSWORD, "name": "A"}).status_code == 404
        assert client.get("/api/teams").status_code == 404
        assert client.get("/api/sessions").status_code == 404


def test_sessions_require_sign_in_and_are_private_to_their_owner(accounts_settings):
    with start(accounts_settings) as client:
        ann, _ = register(client, "ann@example.com")
        bob, _ = register(client, "bob@example.com")
        assert client.post("/api/sessions").status_code == 401
        sid = new_session(client, ann)
        assert upload_small(client, ann, sid).json()["datasets"]
        assert client.get(f"/api/sessions/{sid}", headers=ann).json()["role"] == "owner"
        assert client.get(f"/api/sessions/{sid}", headers=bob).status_code == 404
        assert client.post(f"/api/sessions/{sid}/chat", headers=bob, json={"message": "hi"}).status_code == 404
        assert client.delete(f"/api/sessions/{sid}", headers=bob).status_code == 404
        assert [w["session_id"] for w in client.get("/api/sessions", headers=ann).json()] == [sid]
        assert client.get("/api/sessions", headers=bob).json() == []


def test_team_roles_control_access_to_a_shared_workspace(accounts_settings):
    with start(accounts_settings) as client:
        ann, _ = register(client, "ann@example.com")
        bob, bob_user = register(client, "bob@example.com")
        sid = new_session(client, ann)
        upload_small(client, ann, sid)
        team = client.post("/api/teams", headers=ann, json={"name": "Analytics"}).json()
        assert team["role"] == "admin"
        assert client.post(f"/api/teams/{team['id']}/members", headers=ann, json={"email": "bob@example.com", "role": "viewer"}).status_code == 200
        assert client.get(f"/api/sessions/{sid}", headers=bob).status_code == 404

        moved = client.patch(f"/api/sessions/{sid}", headers=ann, json={"team_id": team["id"]})
        assert moved.status_code == 200 and moved.json()["team_id"] == team["id"]
        view = client.get(f"/api/sessions/{sid}", headers=bob).json()
        assert view["role"] == "reader" and view["datasets"]
        assert client.get(f"/api/sessions/{sid}/datasets/a/preview", headers=bob).status_code == 200
        blocked = upload_small(client, bob, sid)
        assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "read_only"
        assert [w["role"] for w in client.get("/api/sessions", headers=bob).json()] == ["reader"]

        client.post(f"/api/teams/{team['id']}/members", headers=ann, json={"email": "bob@example.com", "role": "member"})
        assert client.get(f"/api/sessions/{sid}", headers=bob).json()["role"] == "writer"
        assert upload_small(client, bob, sid).status_code == 200
        assert client.delete(f"/api/sessions/{sid}", headers=bob).status_code == 403
        assert client.patch(f"/api/sessions/{sid}", headers=bob, json={"name": "mine now"}).status_code == 403

        assert client.delete(f"/api/teams/{team['id']}/members/{bob_user['id']}", headers=ann).status_code == 200
        assert client.get(f"/api/sessions/{sid}", headers=bob).status_code == 404


def test_team_management_rules(accounts_settings):
    with start(accounts_settings) as client:
        ann, ann_user = register(client, "ann@example.com")
        bob, _ = register(client, "bob@example.com")
        carl, _ = register(client, "carl@example.com")
        team = client.post("/api/teams", headers=ann, json={"name": "Core"}).json()
        url = f"/api/teams/{team['id']}/members"
        assert client.post(url, headers=ann, json={"email": "nobody@example.com"}).json()["error"]["code"] == "user_not_found"
        assert client.post(url, headers=ann, json={"email": "bob@example.com", "role": "boss"}).status_code == 422
        client.post(url, headers=ann, json={"email": "bob@example.com", "role": "member"})
        assert client.post(url, headers=bob, json={"email": "carl@example.com"}).status_code == 403
        assert client.get(url, headers=carl).status_code == 404
        assert {m["email"] for m in client.get(url, headers=bob).json()} == {"ann@example.com", "bob@example.com"}
        assert client.delete(f"{url}/{ann_user['id']}", headers=ann).json()["error"]["code"] == "last_admin"
        assert [t["name"] for t in client.get("/api/teams", headers=bob).json()] == ["Core"]
        assert client.get("/api/teams", headers=carl).json() == []


def test_workspace_cannot_be_moved_into_a_team_you_do_not_belong_to(accounts_settings):
    with start(accounts_settings) as client:
        ann, _ = register(client, "ann@example.com")
        bob, _ = register(client, "bob@example.com")
        team = client.post("/api/teams", headers=bob, json={"name": "Bobs"}).json()
        sid = new_session(client, ann)
        assert client.patch(f"/api/sessions/{sid}", headers=ann, json={"team_id": team["id"]}).status_code == 403


def test_rename_workspace_and_listing_order(accounts_settings):
    with start(accounts_settings) as client:
        ann, _ = register(client, "ann@example.com")
        sid = new_session(client, ann)
        renamed = client.patch(f"/api/sessions/{sid}", headers=ann, json={"name": "Q3 revenue review"}).json()
        assert renamed["name"] == "Q3 revenue review"
        assert client.get("/api/sessions", headers=ann).json()[0]["name"] == "Q3 revenue review"
        assert client.patch(f"/api/sessions/{sid}", headers=ann, json={"name": "  "}).status_code == 422


def test_owned_workspaces_never_expire_but_anonymous_ones_do(settings):
    settings.session_ttl_minutes = 1
    with start(settings) as client:
        anonymous = client.post("/api/sessions").json()["session_id"]
        manager = client.app.state.sessions
        manager.sessions[anonymous].last_used -= 3600
        manager.expire_old()
        assert anonymous not in manager.sessions and client.get(f"/api/sessions/{anonymous}").status_code == 404
    settings.auth_mode = "accounts"
    with start(settings) as client:
        ann, _ = register(client, "ann@example.com")
        sid = new_session(client, ann)
        client.app.state.sessions.sessions[sid].last_used -= 3600
        client.app.state.sessions.expire_old()
        assert client.get(f"/api/sessions/{sid}", headers=ann).status_code == 200


def test_idle_sessions_are_unloaded_not_deleted_and_reload_on_demand(accounts_settings):
    accounts_settings.max_sessions = 1
    with start(accounts_settings) as client:
        ann, _ = register(client, "ann@example.com")
        first = new_session(client, ann)
        upload_small(client, ann, first)
        second = new_session(client, ann)
        manager = client.app.state.sessions
        assert first not in manager.sessions and (manager.root / first / "store.duckdb").exists()
        reloaded = client.get(f"/api/sessions/{first}", headers=ann).json()
        assert reloaded["datasets"][0]["profile"]["rows"] == 3
        assert second not in manager.sessions or first in manager.sessions
