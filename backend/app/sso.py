import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.accounts import Accounts, User, hash_token
from app.config import Settings
from app.db import Database
from app.errors import UserError

STATE_SECONDS = 600
CLOCK_SKEW_SECONDS = 120
DISCOVERY_SECONDS = 3600


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def rejected(reason: str) -> UserError:
    return UserError(f"Single sign-on failed: {reason}", "sso_failed", 401)


def public_key(jwk: dict) -> rsa.RSAPublicKey:
    numbers = rsa.RSAPublicNumbers(int.from_bytes(b64url_decode(jwk["e"]), "big"), int.from_bytes(b64url_decode(jwk["n"]), "big"))
    return numbers.public_key()


def verify_id_token(token: str, keys: list[dict], issuer: str, audience: str, nonce: str, now: float | None = None) -> dict:
    try:
        header_part, payload_part, signature_part = token.split(".")
        header = json.loads(b64url_decode(header_part))
        claims = json.loads(b64url_decode(payload_part))
        signature = b64url_decode(signature_part)
    except (ValueError, json.JSONDecodeError) as exc:
        raise rejected("the identity token is malformed.") from exc
    if header.get("alg") != "RS256":
        raise rejected("the identity token uses an unsupported signature type.")
    candidates = [k for k in keys if k.get("kty") == "RSA" and (not header.get("kid") or k.get("kid") == header.get("kid"))]
    if not candidates:
        raise rejected("no matching signing key was found.")
    try:
        public_key(candidates[0]).verify(signature, f"{header_part}.{payload_part}".encode(), padding.PKCS1v15(), hashes.SHA256())
    except (InvalidSignature, KeyError, ValueError) as exc:
        raise rejected("the identity token signature is not valid.") from exc
    current = time.time() if now is None else now
    audiences = claims.get("aud")
    audiences = [audiences] if isinstance(audiences, str) else audiences or []
    if claims.get("iss") != issuer:
        raise rejected("the identity token comes from a different issuer.")
    if audience not in audiences or (len(audiences) > 1 and claims.get("azp") != audience):
        raise rejected("the identity token was not issued for this application.")
    if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] < current - CLOCK_SKEW_SECONDS:
        raise rejected("the identity token has expired.")
    if isinstance(claims.get("nbf"), (int, float)) and claims["nbf"] > current + CLOCK_SKEW_SECONDS:
        raise rejected("the identity token is not valid yet.")
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise rejected("the sign-in request did not match.")
    return claims


class Sso:
    def __init__(self, db: Database, settings: Settings, accounts: Accounts):
        self.db = db
        self.settings = settings
        self.accounts = accounts
        self.cached: tuple[float, dict] | None = None

    def enabled(self) -> bool:
        return bool(self.settings.oidc_issuer and self.settings.oidc_client_id and self.settings.oidc_client_secret)

    def require_enabled(self) -> None:
        if not self.enabled():
            raise UserError("Single sign-on is not set up on this server.", "sso_disabled", 404)

    def redirect_uri(self) -> str:
        return self.settings.public_url.rstrip("/") + "/sso"

    def issuer(self) -> str:
        return self.settings.oidc_issuer.rstrip("/")

    def client(self, transport: httpx.BaseTransport | None) -> httpx.Client:
        return httpx.Client(transport=transport, timeout=self.settings.connector_timeout_seconds, follow_redirects=False)

    def secure(self, url: str) -> None:
        if not url.startswith("https://") and not self.settings.allow_private_connections:
            raise UserError("The identity provider must use https.", "sso_unavailable", 502)

    def get_json(self, client: httpx.Client, url: str) -> dict:
        self.secure(url)
        try:
            response = client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise UserError("The identity provider could not be reached.", "sso_unavailable", 502) from exc

    def discovery(self, client: httpx.Client) -> dict:
        if self.cached and time.time() - self.cached[0] < DISCOVERY_SECONDS:
            return self.cached[1]
        document = self.get_json(client, self.issuer() + "/.well-known/openid-configuration")
        if document.get("issuer", "").rstrip("/") != self.issuer():
            raise UserError("The identity provider answered for a different issuer.", "sso_unavailable", 502)
        self.cached = (time.time(), document)
        return document

    def start(self, transport: httpx.BaseTransport | None = None) -> str:
        self.require_enabled()
        with self.client(transport) as client:
            endpoint = self.discovery(client)["authorization_endpoint"]
        state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        self.db.run("DELETE FROM sso_states WHERE expires_at < ?", (time.time(),))
        self.db.run(
            "INSERT INTO sso_states (state_hash, nonce, verifier, expires_at) VALUES (?, ?, ?, ?)",
            (hash_token(state), nonce, verifier, time.time() + STATE_SECONDS),
        )
        challenge = b64url_encode(hashlib.sha256(verifier.encode()).digest())
        query = urlencode({
            "response_type": "code", "client_id": self.settings.oidc_client_id, "redirect_uri": self.redirect_uri(),
            "scope": self.settings.oidc_scopes, "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256",
        })
        return f"{endpoint}?{query}"

    def take_state(self, state: str) -> dict:
        digest = hash_token(state)
        row = self.db.one("SELECT nonce, verifier FROM sso_states WHERE state_hash = ? AND expires_at > ?", (digest, time.time()))
        if row is None or self.db.run("DELETE FROM sso_states WHERE state_hash = ?", (digest,)) == 0:
            raise rejected("this sign-in request expired. Start again.")
        return row

    def finish(self, code: str, state: str, transport: httpx.BaseTransport | None = None) -> tuple[str, User]:
        self.require_enabled()
        pending = self.take_state(state)
        with self.client(transport) as client:
            document = self.discovery(client)
            self.secure(document["token_endpoint"])
            try:
                response = client.post(document["token_endpoint"], data={
                    "grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri(),
                    "client_id": self.settings.oidc_client_id, "client_secret": self.settings.oidc_client_secret,
                    "code_verifier": pending["verifier"],
                }, headers={"Accept": "application/json"})
            except httpx.HTTPError as exc:
                raise UserError("The identity provider could not be reached.", "sso_unavailable", 502) from exc
            if response.status_code != 200 or "id_token" not in response.text:
                raise rejected("the identity provider did not accept the sign-in.")
            keys = self.get_json(client, document["jwks_uri"]).get("keys", [])
        claims = verify_id_token(response.json()["id_token"], keys, document["issuer"], self.settings.oidc_client_id, pending["nonce"])
        email = str(claims.get("email", "")).strip().lower()
        if not email or claims.get("email_verified") is not True:
            raise rejected("the identity provider did not confirm an email address for you.")
        name = str(claims.get("name") or email.split("@")[0])[:80]
        return self.accounts.sign_in_with_sso(email, name)
