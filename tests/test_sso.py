import hashlib
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi.testclient import TestClient

from app.main import create_app
from app.sso import b64url_encode, verify_id_token
from fakes import ScriptedLLM

ISSUER = "https://idp.example.com"
CLIENT = "datapilot-client"


def jwk_of(key, kid):
    numbers = key.public_key().public_numbers()
    size = (numbers.n.bit_length() + 7) // 8
    return {"kty": "RSA", "kid": kid, "alg": "RS256", "n": b64url_encode(numbers.n.to_bytes(size, "big")), "e": b64url_encode(numbers.e.to_bytes(3, "big"))}


def make_jwt(key, claims, kid="k1", alg="RS256"):
    header = b64url_encode(json.dumps({"alg": alg, "kid": kid, "typ": "JWT"}).encode())
    payload = b64url_encode(json.dumps(claims).encode())
    signature = key.sign(f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{b64url_encode(signature)}"


class FakeIdp:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.profile = {"email": "ann@example.com", "email_verified": True, "name": "Ann Lee"}
        self.override = {}
        self.signer = self.key
        self.issued = {}
        self.token_status = 200
        self.token_calls = 0

    def claims(self, nonce):
        base = {"iss": ISSUER, "aud": CLIENT, "sub": "u1", "exp": time.time() + 600, "iat": time.time(), "nonce": nonce, **self.profile}
        return {**base, **self.override}

    def handler(self, request):
        path = request.url.path
        if path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={
                "issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize", "token_endpoint": f"{ISSUER}/token", "jwks_uri": f"{ISSUER}/jwks",
            })
        if path == "/jwks":
            return httpx.Response(200, json={"keys": [jwk_of(self.key, "k1")]})
        if path == "/token":
            self.token_calls += 1
            form = parse_qs(request.content.decode())
            code = form["code"][0]
            pending = self.issued.get(code)
            if self.token_status != 200 or pending is None:
                return httpx.Response(400, json={"error": "invalid_grant"})
            challenge = b64url_encode(hashlib.sha256(form["code_verifier"][0].encode()).digest())
            assert challenge == pending["challenge"], "PKCE verifier does not match the challenge"
            assert form["client_secret"][0] == "shh" and form["redirect_uri"][0] == "https://app.example.com/sso"
            return httpx.Response(200, json={"id_token": make_jwt(self.signer, self.claims(pending["nonce"])), "access_token": "x"})
        return httpx.Response(404)

    def authorize(self, url):
        query = parse_qs(urlparse(url).query)
        code = f"code-{len(self.issued)}"
        self.issued[code] = {"nonce": query["nonce"][0], "challenge": query["code_challenge"][0]}
        return code, query


@pytest.fixture
def idp():
    return FakeIdp()


@pytest.fixture
def sso_settings(settings):
    settings.auth_mode = "accounts"
    settings.scheduler_enabled = False
    settings.public_url = "https://app.example.com"
    settings.oidc_issuer, settings.oidc_client_id, settings.oidc_client_secret = ISSUER, CLIENT, "shh"
    settings.oidc_name = "Acme SSO"
    settings.login_per_minute = 100
    return settings


@pytest.fixture
def client(sso_settings, idp):
    with TestClient(create_app(sso_settings, lambda s, o=None: ScriptedLLM())) as c:
        c.app.state.http_transport = httpx.MockTransport(idp.handler)
        yield c


def sign_in(client, idp):
    url = client.get("/api/auth/sso/start").json()["url"]
    code, query = idp.authorize(url)
    return client.post("/api/auth/sso/callback", json={"code": code, "state": query["state"][0]}), query


class TestFlow:
    def test_config_advertises_the_provider_only_when_set_up(self, client, sso_settings):
        assert client.get("/api/config").json()["sso_name"] == "Acme SSO"
        sso_settings.oidc_issuer = ""
        assert client.get("/api/config").json()["sso_name"] is None

    def test_start_builds_a_pkce_authorization_url(self, client):
        url = client.get("/api/auth/sso/start").json()["url"]
        query = parse_qs(urlparse(url).query)
        assert url.startswith(f"{ISSUER}/authorize?") and query["client_id"] == [CLIENT] and query["redirect_uri"] == ["https://app.example.com/sso"]
        assert query["code_challenge_method"] == ["S256"] and query["response_type"] == ["code"] and "openid" in query["scope"][0]
        assert len(query["state"][0]) >= 20 and len(query["nonce"][0]) >= 20

    def test_a_first_sign_in_creates_a_verified_account_and_a_session(self, client, idp):
        response, _ = sign_in(client, idp)
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["email"] == "ann@example.com" and body["user"]["name"] == "Ann Lee"
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"}).status_code == 200
        assert client.app.state.db.one("SELECT verified FROM users")["verified"] == 1

    def test_a_second_sign_in_reuses_the_same_account(self, client, idp):
        first, _ = sign_in(client, idp)
        second, _ = sign_in(client, idp)
        assert first.json()["user"]["id"] == second.json()["user"]["id"]
        assert client.app.state.db.one("SELECT count(*) AS n FROM users")["n"] == 1

    def test_it_links_to_an_existing_password_account_with_the_same_email(self, client, idp):
        registered = client.post("/api/auth/register", json={"email": "ann@example.com", "password": "correct horse battery", "name": "Ann"}).json()
        response, _ = sign_in(client, idp)
        assert response.json()["user"]["id"] == registered["user"]["id"]

    def test_sso_skips_the_local_second_factor(self, client, idp):
        sign_in(client, idp)
        client.app.state.db.run("UPDATE users SET totp_enabled = 1")
        assert sign_in(client, idp)[0].status_code == 200


class TestRejections:
    def test_state_is_single_use_and_unknown_states_fail(self, client, idp):
        url = client.get("/api/auth/sso/start").json()["url"]
        code, query = idp.authorize(url)
        body = {"code": code, "state": query["state"][0]}
        assert client.post("/api/auth/sso/callback", json=body).status_code == 200
        replay = client.post("/api/auth/sso/callback", json=body)
        assert replay.status_code == 401 and replay.json()["error"]["code"] == "sso_failed"
        assert client.post("/api/auth/sso/callback", json={"code": "x", "state": "never-issued-state-value"}).status_code == 401

    def test_states_expire(self, client, idp):
        url = client.get("/api/auth/sso/start").json()["url"]
        code, query = idp.authorize(url)
        client.app.state.db.run("UPDATE sso_states SET expires_at = 1")
        assert client.post("/api/auth/sso/callback", json={"code": code, "state": query["state"][0]}).status_code == 401

    def test_unverified_or_missing_email_is_refused(self, client, idp):
        idp.profile = {"email": "ann@example.com", "email_verified": False}
        assert sign_in(client, idp)[0].status_code == 401
        idp.profile = {"name": "No Email"}
        assert sign_in(client, idp)[0].status_code == 401
        assert client.app.state.db.one("SELECT count(*) AS n FROM users")["n"] == 0

    @pytest.mark.parametrize("override", [
        {"iss": "https://evil.example.com"}, {"aud": "someone-else"}, {"exp": 1}, {"nonce": "wrong"}, {"nbf": 4_000_000_000},
    ])
    def test_bad_claims_are_refused(self, client, idp, override):
        idp.override = override
        response, _ = sign_in(client, idp)
        assert response.status_code == 401 and response.json()["error"]["code"] == "sso_failed"

    def test_a_token_signed_with_another_key_is_refused(self, client, idp):
        idp.signer = idp.other_key
        assert sign_in(client, idp)[0].status_code == 401

    def test_the_provider_rejecting_the_code_is_a_clean_failure(self, client, idp):
        idp.token_status = 400
        response, _ = sign_in(client, idp)
        assert response.status_code == 401 and idp.token_calls == 1

    def test_an_unreachable_provider_is_reported(self, client):
        def down(request):
            raise httpx.ConnectError("down")

        client.app.state.http_transport = httpx.MockTransport(down)
        client.app.state.sso.cached = None
        assert client.get("/api/auth/sso/start").status_code == 502

    def test_an_issuer_mismatch_in_discovery_is_refused(self, client):
        def wrong(request):
            return httpx.Response(200, json={"issuer": "https://other.example.com", "authorization_endpoint": "x", "token_endpoint": "y", "jwks_uri": "z"})

        client.app.state.http_transport = httpx.MockTransport(wrong)
        client.app.state.sso.cached = None
        assert client.get("/api/auth/sso/start").status_code == 502

    def test_plain_http_providers_need_the_private_flag(self, client, sso_settings):
        sso_settings.oidc_issuer = "http://idp.example.com"
        client.app.state.sso.cached = None
        assert client.get("/api/auth/sso/start").status_code == 502

    def test_unavailable_without_configuration(self, client, sso_settings):
        sso_settings.oidc_issuer = ""
        assert client.get("/api/auth/sso/start").status_code == 404


class TestPolicies:
    def test_the_email_domain_restriction_applies(self, client, idp, sso_settings):
        sso_settings.allowed_email_domain = "corp.example.com"
        response, _ = sign_in(client, idp)
        assert response.status_code == 403 and response.json()["error"]["code"] == "email_domain_not_allowed"

    def test_closed_registration_blocks_new_accounts_but_not_existing_ones(self, client, idp, sso_settings):
        sso_settings.registration = "closed"
        assert sign_in(client, idp)[0].status_code == 403
        sso_settings.registration = "open"
        sign_in(client, idp)
        sso_settings.registration = "closed"
        assert sign_in(client, idp)[0].status_code == 200

    def test_sso_is_unavailable_outside_accounts_mode(self, settings):
        with TestClient(create_app(settings, lambda s, o=None: ScriptedLLM())) as c:
            assert c.get("/api/auth/sso/start").status_code == 404


class TestTokenChecks:
    def test_hmac_and_none_algorithms_are_refused(self, idp):
        keys = [jwk_of(idp.key, "k1")]
        claims = idp.claims("n")
        for alg in ("none", "HS256"):
            header = b64url_encode(json.dumps({"alg": alg}).encode())
            token = f"{header}.{b64url_encode(json.dumps(claims).encode())}.{b64url_encode(b'sig')}"
            with pytest.raises(Exception) as caught:
                verify_id_token(token, keys, ISSUER, CLIENT, "n")
            assert "unsupported" in caught.value.message

    def test_multiple_audiences_need_a_matching_authorized_party(self, idp):
        keys = [jwk_of(idp.key, "k1")]
        token = make_jwt(idp.key, idp.claims("n") | {"aud": [CLIENT, "other"]})
        with pytest.raises(Exception):
            verify_id_token(token, keys, ISSUER, CLIENT, "n")
        assert verify_id_token(make_jwt(idp.key, idp.claims("n") | {"aud": [CLIENT, "other"], "azp": CLIENT}), keys, ISSUER, CLIENT, "n")["sub"] == "u1"

    def test_garbage_is_a_clean_failure(self, idp):
        with pytest.raises(Exception) as caught:
            verify_id_token("not.a.jwt", [jwk_of(idp.key, "k1")], ISSUER, CLIENT, "n")
        assert "malformed" in caught.value.message
