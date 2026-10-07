import re
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import UserError
from app.mailer import Mailer
from app.main import create_app
from fakes import ScriptedLLM
from smtp_sink import SmtpSink

PASSWORD = "correct horse battery"
NEW_PASSWORD = "an entirely new passphrase"


@pytest.fixture
def sink():
    smtp = SmtpSink().start()
    yield smtp
    smtp.stop()


@pytest.fixture
def mail_settings(settings, sink):
    settings.auth_mode = "accounts"
    settings.scheduler_enabled = False
    settings.schedule_min_minutes = 1
    settings.smtp_host, settings.smtp_port, settings.smtp_security = "127.0.0.1", sink.port, "none"
    settings.smtp_from = "DataPilot <noreply@example.com>"
    settings.public_url = "https://app.example.com"
    return settings


def start(settings):
    return TestClient(create_app(settings, lambda s, o=None: ScriptedLLM()))


def register(client, email="ann@example.com", name="Ann"):
    return client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "name": name})


def link_token(message, path):
    match = re.search(rf"https://app\.example\.com/{path}\?token=([A-Za-z0-9_-]+)", SmtpSink.body(message))
    assert match, SmtpSink.body(message)
    return match.group(1)


class TestMailer:
    def test_delivers_a_plain_text_message(self, mail_settings, sink):
        assert Mailer(mail_settings).send_now("ann@example.com", "Hello", "Body text") is True
        (message,) = sink.wait_for(1)
        assert message["Subject"] == "Hello" and message["To"] == "ann@example.com" and "noreply@example.com" in message["From"]
        assert SmtpSink.body(message).strip() == "Body text"

    def test_is_silent_when_smtp_is_not_configured(self, settings):
        mailer = Mailer(settings)
        assert mailer.enabled is False and mailer.send_now("a@b.co", "s", "b") is False
        mailer.send("a@b.co", "s", "b")

    def test_header_injection_is_rejected(self, mail_settings):
        mailer = Mailer(mail_settings)
        for to, subject in [("a@b.co\r\nBcc: x@y.z", "s"), ("a@b.co", "s\r\nBcc: x@y.z")]:
            with pytest.raises(UserError):
                mailer.build(to, subject, "body")

    def test_delivery_failures_are_swallowed_and_reported_as_false(self, mail_settings):
        mail_settings.smtp_port = 1
        assert Mailer(mail_settings).send_now("a@b.co", "s", "b") is False

    def test_starttls_and_login_are_used_when_configured(self, mail_settings, monkeypatch):
        calls = []

        class FakeSmtp:
            def __init__(self, host, port, timeout):
                calls.append(("connect", host, port))

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def starttls(self, context):
                calls.append(("starttls", context.check_hostname))

            def login(self, user, password):
                calls.append(("login", user))

            def send_message(self, message):
                calls.append(("send", message["To"]))

        monkeypatch.setattr("app.mailer.smtplib.SMTP", FakeSmtp)
        mail_settings.smtp_security, mail_settings.smtp_user, mail_settings.smtp_password = "starttls", "mailer", "secret"
        assert Mailer(mail_settings).send_now("ann@example.com", "s", "b") is True
        assert [c[0] for c in calls] == ["connect", "starttls", "login", "send"] and calls[1][1] is True


class TestPasswordReset:
    def test_full_reset_flow(self, mail_settings, sink):
        with start(mail_settings) as client:
            old_token = register(client).json()["token"]
            assert client.post("/api/auth/forgot", json={"email": "ann@example.com"}).json() == {"sent": True}
            (message,) = sink.wait_for(1)
            assert message["To"] == "ann@example.com"
            token = link_token(message, "reset")
            stored = str(client.app.state.db.all("SELECT token_hash FROM email_tokens"))
            assert token not in stored

            assert client.post("/api/auth/reset", json={"token": token, "password": "short"}).json()["error"]["code"] == "weak_password"
            assert client.post("/api/auth/reset", json={"token": token, "password": NEW_PASSWORD}).json() == {"reset": True}
            assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
            assert client.post("/api/auth/login", json={"email": "ann@example.com", "password": PASSWORD}).status_code == 401
            assert client.post("/api/auth/login", json={"email": "ann@example.com", "password": NEW_PASSWORD}).status_code == 200
            notice = sink.wait_for(2)[1]
            assert "password was changed" in notice["Subject"]

    def test_reset_links_work_once_and_expire(self, mail_settings, sink):
        with start(mail_settings) as client:
            register(client)
            client.post("/api/auth/forgot", json={"email": "ann@example.com"})
            token = link_token(sink.wait_for(1)[0], "reset")
            assert client.post("/api/auth/reset", json={"token": token, "password": NEW_PASSWORD}).status_code == 200
            assert client.post("/api/auth/reset", json={"token": token, "password": "yet another phrase!"}).json()["error"]["code"] == "invalid_link"
            client.post("/api/auth/forgot", json={"email": "ann@example.com"})
            expired = link_token(sink.wait_for(3)[2], "reset")
            client.app.state.db.run("UPDATE email_tokens SET expires_at = ?", (time.time() - 5,))
            assert client.post("/api/auth/reset", json={"token": expired, "password": NEW_PASSWORD}).json()["error"]["code"] == "invalid_link"
            assert client.post("/api/auth/reset", json={"token": "x" * 40, "password": NEW_PASSWORD}).status_code == 400

    def test_a_new_request_invalidates_the_previous_link(self, mail_settings, sink):
        with start(mail_settings) as client:
            register(client)
            client.post("/api/auth/forgot", json={"email": "ann@example.com"})
            first = link_token(sink.wait_for(1)[0], "reset")
            client.post("/api/auth/forgot", json={"email": "ann@example.com"})
            second = link_token(sink.wait_for(2)[1], "reset")
            assert client.post("/api/auth/reset", json={"token": first, "password": NEW_PASSWORD}).status_code == 400
            assert client.post("/api/auth/reset", json={"token": second, "password": NEW_PASSWORD}).status_code == 200

    def test_unknown_emails_get_the_same_answer_and_no_mail(self, mail_settings, sink):
        with start(mail_settings) as client:
            register(client)
            known = client.post("/api/auth/forgot", json={"email": "ann@example.com"})
            unknown = client.post("/api/auth/forgot", json={"email": "nobody@example.com"})
            assert known.status_code == unknown.status_code == 200 and known.json() == unknown.json()
            assert sink.settle() == 1

    def test_links_use_the_configured_public_url_not_the_host_header(self, mail_settings, sink):
        with start(mail_settings) as client:
            register(client)
            client.post("/api/auth/forgot", json={"email": "ann@example.com"}, headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"})
            body = SmtpSink.body(sink.wait_for(1)[0])
            assert "https://app.example.com/reset?token=" in body and "evil.example" not in body

    def test_requests_are_rate_limited_per_email(self, mail_settings, sink):
        mail_settings.forgot_per_hour = 2
        with start(mail_settings) as client:
            register(client)
            codes = [client.post("/api/auth/forgot", json={"email": "ann@example.com"}).status_code for _ in range(3)]
            assert codes == [200, 200, 429]

    def test_feature_is_unavailable_without_email_setup(self, settings):
        settings.auth_mode = "accounts"
        with start(settings) as client:
            response = client.post("/api/auth/forgot", json={"email": "ann@example.com"})
            assert response.status_code == 501 and response.json()["error"]["code"] == "email_disabled"
            assert client.get("/api/config").json()["email_enabled"] is False

    def test_config_reports_email_support(self, mail_settings):
        with start(mail_settings) as client:
            assert client.get("/api/config").json()["email_enabled"] is True


class TestEmailVerification:
    def test_new_accounts_must_confirm_their_email_before_signing_in(self, mail_settings, sink):
        mail_settings.require_email_verification = True
        with start(mail_settings) as client:
            created = register(client).json()
            assert created["verification_required"] is True and created["token"] is None
            blocked = client.post("/api/auth/login", json={"email": "ann@example.com", "password": PASSWORD})
            assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "email_not_verified"
            token = link_token(sink.wait_for(1)[0], "verify")
            assert client.post("/api/auth/verify", json={"token": token}).json() == {"verified": True}
            assert client.post("/api/auth/login", json={"email": "ann@example.com", "password": PASSWORD}).status_code == 200
            assert client.post("/api/auth/verify", json={"token": token}).json()["error"]["code"] == "invalid_link"
            assert client.get("/api/config").json()["email_verification_required"] is True

    def test_resending_replaces_the_old_link_and_never_reveals_accounts(self, mail_settings, sink):
        mail_settings.require_email_verification = True
        with start(mail_settings) as client:
            register(client)
            first = link_token(sink.wait_for(1)[0], "verify")
            assert client.post("/api/auth/resend-verification", json={"email": "ann@example.com"}).json() == {"sent": True}
            assert client.post("/api/auth/resend-verification", json={"email": "ghost@example.com"}).json() == {"sent": True}
            second = link_token(sink.wait_for(2)[1], "verify")
            assert sink.settle() == 2
            assert client.post("/api/auth/verify", json={"token": first}).status_code == 400
            assert client.post("/api/auth/verify", json={"token": second}).status_code == 200

    def test_resetting_a_password_also_proves_ownership_of_the_email(self, mail_settings, sink):
        mail_settings.require_email_verification = True
        with start(mail_settings) as client:
            register(client)
            client.post("/api/auth/forgot", json={"email": "ann@example.com"})
            reset_mail = next(m for m in sink.wait_for(2) if "Reset" in m["Subject"])
            reset = link_token(reset_mail, "reset")
            client.post("/api/auth/reset", json={"token": reset, "password": NEW_PASSWORD})
            assert client.post("/api/auth/login", json={"email": "ann@example.com", "password": NEW_PASSWORD}).status_code == 200

    def test_verification_is_skipped_when_email_is_not_configured(self, settings):
        settings.auth_mode = "accounts"
        settings.require_email_verification = True
        with start(settings) as client:
            created = register(client).json()
            assert created["token"] and created["verification_required"] is False

    def test_existing_accounts_stay_verified_after_the_upgrade(self, mail_settings):
        with start(mail_settings) as client:
            register(client)
            assert client.app.state.db.one("SELECT verified FROM users")["verified"] == 1


class TestChangePassword:
    def test_requires_the_current_password_and_keeps_only_this_session(self, mail_settings, sink):
        with start(mail_settings) as client:
            first = register(client).json()["token"]
            second = client.post("/api/auth/login", json={"email": "ann@example.com", "password": PASSWORD}).json()["token"]
            headers = {"Authorization": f"Bearer {first}"}
            wrong = client.post("/api/auth/password", headers=headers, json={"current_password": "not my password", "new_password": NEW_PASSWORD})
            assert wrong.status_code == 403
            assert client.post("/api/auth/password", headers=headers, json={"current_password": PASSWORD, "new_password": "short"}).status_code == 422
            assert client.post("/api/auth/password", headers=headers, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}).json() == {"changed": True}
            assert client.get("/api/auth/me", headers=headers).status_code == 200
            assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {second}"}).status_code == 401
            assert client.post("/api/auth/login", json={"email": "ann@example.com", "password": NEW_PASSWORD}).status_code == 200
            assert "password was changed" in sink.wait_for(1)[0]["Subject"]

    def test_requires_sign_in(self, mail_settings):
        with start(mail_settings) as client:
            assert client.post("/api/auth/password", json={"current_password": "x", "new_password": NEW_PASSWORD}).status_code == 401


class TestScheduleNotifications:
    def setup_schedule(self, client, **extra):
        token = register(client).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        sid = client.post("/api/sessions", headers=headers).json()["session_id"]
        client.post(f"/api/sessions/{sid}/samples", headers=headers)
        body = {"name": "Revenue check", "sql": "SELECT region, sum(revenue) AS total FROM orders GROUP BY 1", "every_minutes": 60, **extra}
        created = client.post(f"/api/sessions/{sid}/schedules", headers=headers, json=body)
        return sid, headers, created

    def test_failure_mode_only_emails_when_a_run_fails(self, mail_settings, sink):
        with start(mail_settings) as client:
            sid, headers, created = self.setup_schedule(client, notify="failure")
            schedule_id = created.json()["id"]
            client.post(f"/api/sessions/{sid}/schedules/{schedule_id}/run", headers=headers)
            assert sink.settle() == 0
            client.delete(f"/api/sessions/{sid}/datasets/orders", headers=headers)
            client.post(f"/api/sessions/{sid}/schedules/{schedule_id}/run", headers=headers)
            (message,) = sink.wait_for(1)
            assert "failed" in message["Subject"] and "Revenue check" in message["Subject"] and message["To"] == "ann@example.com"
            assert "orders" in SmtpSink.body(message)

    def test_always_mode_sends_a_summary_without_any_data(self, mail_settings, sink):
        with start(mail_settings) as client:
            sid, headers, created = self.setup_schedule(client, notify="always")
            client.post(f"/api/sessions/{sid}/schedules/{created.json()['id']}/run", headers=headers)
            (message,) = sink.wait_for(1)
            body = SmtpSink.body(message)
            assert "ran successfully" in message["Subject"] and "returned 5 rows" in body
            assert "North America" not in body and "3275899" not in body and "Europe" not in body

    def test_notifications_need_email_and_a_valid_mode(self, settings):
        settings.auth_mode = "accounts"
        settings.schedule_min_minutes = 1
        with start(settings) as client:
            _, _, created = self.setup_schedule(client, notify="always")
            assert created.status_code == 501 and created.json()["error"]["code"] == "email_disabled"

    def test_invalid_notify_value_is_rejected(self, mail_settings):
        with start(mail_settings) as client:
            _, _, created = self.setup_schedule(client, notify="sometimes")
            assert created.status_code == 422

    def test_schedules_default_to_no_email(self, mail_settings, sink):
        with start(mail_settings) as client:
            sid, headers, created = self.setup_schedule(client)
            assert created.json()["notify"] == "none"
            client.delete(f"/api/sessions/{sid}/datasets/orders", headers=headers)
            client.post(f"/api/sessions/{sid}/schedules/{created.json()['id']}/run", headers=headers)
            assert sink.settle() == 0
