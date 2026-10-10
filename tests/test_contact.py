import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from fakes import ScriptedLLM
from smtp_sink import SmtpSink

MESSAGE = "We would like to try DataPilot with a team of eight analysts."


@pytest.fixture
def sink():
    smtp = SmtpSink().start()
    yield smtp
    smtp.stop()


@pytest.fixture
def contact_settings(settings, sink):
    settings.scheduler_enabled = False
    settings.smtp_host, settings.smtp_port, settings.smtp_security = "127.0.0.1", sink.port, "none"
    settings.smtp_from = "DataPilot <noreply@example.com>"
    settings.contact_email = "hello@example.com"
    return settings


def start(settings):
    return TestClient(create_app(settings, lambda s, o=None: ScriptedLLM()))


def payload(**overrides):
    body = {"name": "Ann Lee", "email": "ann@example.com", "topic": "sales", "message": MESSAGE}
    body.update(overrides)
    return body


def test_message_is_delivered_with_reply_to(contact_settings, sink):
    with start(contact_settings) as client:
        assert client.get("/api/config").json()["contact_form"] is True
        response = client.post("/api/contact", json=payload())
        assert response.status_code == 200 and response.json() == {"sent": True}
        (message,) = sink.wait_for(1)
    assert message["To"] == "hello@example.com"
    assert message["Reply-To"] == "ann@example.com"
    assert message["Subject"] == "[DataPilot] Sales and teams from Ann Lee"
    assert MESSAGE in SmtpSink.body(message)


def test_disabled_without_contact_address(settings):
    with start(settings) as client:
        assert client.get("/api/config").json()["contact_form"] is False
        response = client.post("/api/contact", json=payload())
    assert response.status_code == 404 and response.json()["error"]["code"] == "contact_disabled"


@pytest.mark.parametrize(
    "overrides, code",
    [
        ({"name": "   "}, "invalid_name"),
        ({"email": "not-an-email"}, "invalid_email"),
        ({"email": "ann@example.com\r\nBcc: x@y.z"}, "invalid_email"),
        ({"message": "too short"}, "invalid_message"),
    ],
)
def test_invalid_fields_get_specific_errors(contact_settings, overrides, code):
    with start(contact_settings) as client:
        response = client.post("/api/contact", json=payload(**overrides))
    assert response.status_code == 422 and response.json()["error"]["code"] == code


def test_newlines_in_name_cannot_inject_headers(contact_settings, sink):
    with start(contact_settings) as client:
        assert client.post("/api/contact", json=payload(name="Ann\r\nBcc: evil@example.com")).status_code == 200
        (message,) = sink.wait_for(1)
    assert message["Bcc"] is None and message["Subject"].endswith("Ann Bcc: evil@example.com")


def test_honeypot_is_accepted_silently_and_not_sent(contact_settings, sink):
    with start(contact_settings) as client:
        assert client.post("/api/contact", json=payload(website="http://spam.example")).json() == {"sent": True}
    assert sink.messages == []


def test_rate_limited_per_ip(contact_settings):
    contact_settings.contact_per_hour = 2
    with start(contact_settings) as client:
        codes = [client.post("/api/contact", json=payload(website="x")).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
