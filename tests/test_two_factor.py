import base64
import os
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app import twofactor
from app.errors import UserError
from app.main import create_app
from fakes import ScriptedLLM

PASSWORD = "correct horse battery"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def tf_settings(settings):
    settings.auth_mode = "accounts"
    settings.scheduler_enabled = False
    settings.secret_key = Fernet.generate_key().decode()
    settings.login_per_minute = 100
    return settings


def start(settings):
    return TestClient(create_app(settings, lambda s, o=None: ScriptedLLM()))


def register(client, email="ann@example.com"):
    return client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "name": "Ann"}).json()["token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def turn_on(client, token):
    setup = client.post("/api/auth/2fa/setup", headers=auth(token), json={"password": PASSWORD})
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    code = twofactor.code_at(secret, twofactor.current_step())
    enabled = client.post("/api/auth/2fa/enable", headers=auth(token), json={"code": code})
    assert enabled.status_code == 200, enabled.text
    return secret, enabled.json()["recovery_codes"]


def next_code(secret):
    return twofactor.code_at(secret, twofactor.current_step() + 1)


def password_login(client, email="ann@example.com"):
    return client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()


def run_admin(args, root):
    env = {"UPLOAD_ROOT": str(root), "PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    return subprocess.run([sys.executable, "-m", "app.admin", *args], cwd=ROOT / "backend", env=env, capture_output=True, text=True)


class TestPrimitives:
    def test_matches_the_rfc_6238_vectors(self):
        secret = base64.b32encode(b"12345678901234567890").decode()
        vectors = {59: "287082", 1111111109: "081804", 1111111111: "050471", 1234567890: "005924", 2000000000: "279037"}
        for seconds, expected in vectors.items():
            assert twofactor.code_at(secret, seconds // 30) == expected

    def test_accepts_one_step_of_clock_drift_but_not_more(self):
        secret = twofactor.new_secret()
        now = 1_700_000_000
        step = twofactor.current_step(now)
        assert twofactor.verify_code(secret, twofactor.code_at(secret, step - 1), now=now) == step - 1
        assert twofactor.verify_code(secret, twofactor.code_at(secret, step + 1), now=now) == step + 1
        assert twofactor.verify_code(secret, twofactor.code_at(secret, step - 2), now=now) is None
        assert twofactor.verify_code(secret, twofactor.code_at(secret, step + 2), now=now) is None

    def test_rejects_malformed_codes_and_replays(self):
        secret = twofactor.new_secret()
        now = 1_700_000_000
        step = twofactor.current_step(now)
        good = twofactor.code_at(secret, step)
        assert twofactor.verify_code(secret, "12345", now=now) is None
        assert twofactor.verify_code(secret, "abcdef", now=now) is None
        assert twofactor.verify_code(secret, good, last_step=step, now=now) is None
        assert twofactor.verify_code(secret, f"{good[:3]} {good[3:]}", now=now) == step

    def test_recovery_codes_are_unique_and_normalised(self):
        codes = twofactor.new_recovery_codes()
        assert len(set(codes)) == twofactor.RECOVERY_CODE_COUNT
        assert twofactor.hash_recovery_code(codes[0].upper()) == twofactor.hash_recovery_code(codes[0])


class TestSetup:
    def test_needs_a_secret_key_on_the_server(self, tf_settings):
        tf_settings.secret_key = ""
        with start(tf_settings) as client:
            assert client.get("/api/config").json()["two_factor_available"] is False
            token = register(client)
            response = client.post("/api/auth/2fa/setup", headers=auth(token), json={"password": PASSWORD})
            assert response.status_code == 501 and response.json()["error"]["code"] == "two_factor_unavailable"

    def test_setup_needs_the_password_and_the_secret_is_stored_encrypted(self, tf_settings):
        with start(tf_settings) as client:
            token = register(client)
            assert client.post("/api/auth/2fa/setup", headers=auth(token), json={"password": "wrong password"}).status_code == 403
            setup = client.post("/api/auth/2fa/setup", headers=auth(token), json={"password": PASSWORD}).json()
            assert setup["uri"].startswith("otpauth://totp/DataPilot") and "<svg" in setup["qr_svg"]
            stored = client.app.state.db.one("SELECT totp_secret FROM users")["totp_secret"]
            assert setup["secret"] not in stored

    def test_it_stays_off_until_a_valid_code_confirms_it(self, tf_settings):
        with start(tf_settings) as client:
            token = register(client)
            client.post("/api/auth/2fa/setup", headers=auth(token), json={"password": PASSWORD})
            assert client.post("/api/auth/2fa/enable", headers=auth(token), json={"code": "000000"}).status_code == 422
            assert client.get("/api/auth/2fa", headers=auth(token)).json()["enabled"] is False
            assert password_login(client)["token"]

    def test_enabling_returns_recovery_codes_and_signs_out_other_sessions(self, tf_settings):
        with start(tf_settings) as client:
            token = register(client)
            other = password_login(client)["token"]
            _, codes = turn_on(client, token)
            assert len(codes) == 10
            assert client.get("/api/auth/2fa", headers=auth(token)).json() == {"available": True, "enabled": True, "recovery_remaining": 10}
            assert client.get("/api/auth/me", headers=auth(token)).status_code == 200
            assert client.get("/api/auth/me", headers=auth(other)).status_code == 401

    def test_setup_cannot_be_restarted_while_on(self, tf_settings):
        with start(tf_settings) as client:
            token = register(client)
            turn_on(client, token)
            assert client.post("/api/auth/2fa/setup", headers=auth(token), json={"password": PASSWORD}).status_code == 409


class TestSignIn:
    def test_a_password_alone_no_longer_gives_a_session(self, tf_settings):
        with start(tf_settings) as client:
            token = register(client)
            turn_on(client, token)
            result = password_login(client)
            assert result["token"] is None and result["two_factor_required"] is True and result["challenge"]

    def test_a_valid_code_completes_the_sign_in_once(self, tf_settings):
        with start(tf_settings) as client:
            token = register(client)
            secret, _ = turn_on(client, token)
            challenge = password_login(client)["challenge"]
            code = next_code(secret)
            done = client.post("/api/auth/login/2fa", json={"challenge": challenge, "code": code})
            assert done.status_code == 200 and client.get("/api/auth/me", headers=auth(done.json()["token"])).status_code == 200
            again = client.post("/api/auth/login/2fa", json={"challenge": challenge, "code": code})
            assert again.status_code == 401 and again.json()["error"]["code"] == "challenge_expired"

    def test_a_used_code_cannot_be_replayed_on_a_new_sign_in(self, tf_settings):
        with start(tf_settings) as client:
            token = register(client)
            secret, _ = turn_on(client, token)
            code = next_code(secret)
            first = client.post("/api/auth/login/2fa", json={"challenge": password_login(client)["challenge"], "code": code})
            assert first.status_code == 200
            replay = client.post("/api/auth/login/2fa", json={"challenge": password_login(client)["challenge"], "code": code})
            assert replay.status_code == 401 and replay.json()["error"]["code"] == "invalid_code"

    def test_a_wrong_code_keeps_the_challenge_open_for_a_retry(self, tf_settings):
        with start(tf_settings) as client:
            token = register(client)
            secret, _ = turn_on(client, token)
            challenge = password_login(client)["challenge"]
            assert client.post("/api/auth/login/2fa", json={"challenge": challenge, "code": "000000"}).json()["error"]["code"] == "invalid_code"
            assert client.post("/api/auth/login/2fa", json={"challenge": challenge, "code": next_code(secret)}).status_code == 200

    def test_challenges_expire(self, tf_settings):
        with start(tf_settings) as client:
            token = register(client)
            secret, _ = turn_on(client, token)
            challenge = password_login(client)["challenge"]
            client.app.state.db.run("UPDATE email_tokens SET expires_at = 1 WHERE purpose = '2fa'")
            expired = client.post("/api/auth/login/2fa", json={"challenge": challenge, "code": next_code(secret)})
            assert expired.status_code == 401 and expired.json()["error"]["code"] == "challenge_expired"

    def test_guessing_is_rate_limited_per_account(self, tf_settings):
        with start(tf_settings) as client:
            token = register(client)
            turn_on(client, token)
            challenge = password_login(client)["challenge"]
            statuses = [client.post("/api/auth/login/2fa", json={"challenge": challenge, "code": "000000"}).status_code for _ in range(12)]
            assert statuses[:10] == [401] * 10 and statuses[10:] == [429, 429]

    def test_a_password_reset_does_not_bypass_the_code(self, tf_settings):
        with start(tf_settings) as client:
            token = register(client)
            turn_on(client, token)
            user_id = client.app.state.db.one("SELECT id FROM users")["id"]
            client.app.state.accounts.set_password(user_id, "a brand new passphrase")
            result = client.post("/api/auth/login", json={"email": "ann@example.com", "password": "a brand new passphrase"}).json()
            assert result["token"] is None and result["two_factor_required"] is True

    def test_direct_login_helper_refuses_two_factor_accounts(self, tf_settings):
        with start(tf_settings) as client:
            token = register(client)
            turn_on(client, token)
            with pytest.raises(UserError) as caught:
                client.app.state.accounts.login("ann@example.com", PASSWORD)
            assert caught.value.code == "two_factor_required"


class TestRecoveryCodes:
    def test_a_recovery_code_works_once(self, tf_settings):
        with start(tf_settings) as client:
            token = register(client)
            _, codes = turn_on(client, token)
            first = client.post("/api/auth/login/2fa", json={"challenge": password_login(client)["challenge"], "code": codes[0].upper()})
            assert first.status_code == 200
            second = client.post("/api/auth/login/2fa", json={"challenge": password_login(client)["challenge"], "code": codes[0]})
            assert second.status_code == 401
            status = client.get("/api/auth/2fa", headers=auth(first.json()["token"])).json()
            assert status["recovery_remaining"] == 9

    def test_recovery_codes_are_stored_hashed(self, tf_settings):
        with start(tf_settings) as client:
            token = register(client)
            _, codes = turn_on(client, token)
            stored = {row["code_hash"] for row in client.app.state.db.all("SELECT code_hash FROM recovery_codes")}
            assert not stored & set(codes) and len(stored) == 10


class TestDisable:
    def test_needs_the_password_and_a_code(self, tf_settings):
        with start(tf_settings) as client:
            token = register(client)
            secret, codes = turn_on(client, token)
            bad_password = client.post("/api/auth/2fa/disable", headers=auth(token), json={"password": "wrong password", "code": codes[0]})
            assert bad_password.status_code == 403
            bad_code = client.post("/api/auth/2fa/disable", headers=auth(token), json={"password": PASSWORD, "code": "000000"})
            assert bad_code.status_code == 401
            ok = client.post("/api/auth/2fa/disable", headers=auth(token), json={"password": PASSWORD, "code": next_code(secret)})
            assert ok.json() == {"disabled": True}
            assert client.get("/api/auth/2fa", headers=auth(token)).json()["enabled"] is False
            assert password_login(client)["token"]
            assert client.app.state.db.all("SELECT * FROM recovery_codes") == []


class TestAdminCommand:
    def test_disable_command_unlocks_an_account(self, tf_settings, tmp_path):
        tf_settings.upload_root = str(tmp_path / "admin-root")
        with start(tf_settings) as client:
            token = register(client)
            turn_on(client, token)
            assert password_login(client)["two_factor_required"] is True
        done = run_admin(["disable-2fa", "ANN@example.com"], tf_settings.upload_root)
        assert done.returncode == 0, done.stderr
        with start(tf_settings) as client:
            assert password_login(client)["token"]

    def test_unknown_accounts_are_reported(self, tmp_path):
        done = run_admin(["disable-2fa", "nobody@example.com"], tmp_path / "empty")
        assert done.returncode == 1 and "No account" in done.stdout
