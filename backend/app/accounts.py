import hashlib
import hmac
import os
import re
import secrets
import time
import uuid

from pydantic import BaseModel

from app.config import Settings
from app.db import Database
from app.errors import UserError
from app.mailer import Mailer
from app.secrets_box import SecretBox
from app import twofactor

EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
TEAM_ROLES = {"admin", "member", "viewer"}
SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
CHALLENGE_SECONDS = 300
DUMMY_HASH = "scrypt$" + "00" * 16 + "$" + "00" * 32


class User(BaseModel):
    id: str
    email: str
    name: str


class Team(BaseModel):
    id: str
    name: str
    role: str


class Member(BaseModel):
    user_id: str
    email: str
    name: str
    role: str


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, expected = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **SCRYPT)
        return hmac.compare_digest(digest.hex(), expected)
    except ValueError:
        return False


def compose(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Accounts:
    def __init__(self, db: Database, settings: Settings, mailer: Mailer):
        self.db = db
        self.settings = settings
        self.mailer = mailer
        self.box = SecretBox(settings.secret_key)

    def two_factor_available(self) -> bool:
        return bool(self.settings.secret_key)

    def needs_verification(self) -> bool:
        return self.settings.require_email_verification and self.mailer.enabled

    def register(self, email: str, password: str, name: str) -> User:
        if self.settings.registration != "open":
            raise UserError("Registration is closed on this server.", "registration_closed", 403)
        email = email.strip().lower()
        if not EMAIL_PATTERN.match(email):
            raise UserError("Enter a valid email address.", "invalid_email", 422)
        domain = self.settings.allowed_email_domain.strip().lower()
        if domain and not email.endswith("@" + domain):
            raise UserError(f"Only {domain} email addresses can register on this server.", "email_domain_not_allowed", 403)
        if not 10 <= len(password) <= 200:
            raise UserError("Choose a password between 10 and 200 characters.", "weak_password", 422)
        name = name.strip()
        if not 1 <= len(name) <= 80:
            raise UserError("Enter a name of up to 80 characters.", "invalid_name", 422)
        if self.db.one("SELECT id FROM users WHERE email = ?", (email,)):
            raise UserError("An account with this email already exists.", "email_taken", 409)
        user = User(id=uuid.uuid4().hex, email=email, name=name)
        verified = 0 if self.needs_verification() else 1
        self.db.run(
            "INSERT INTO users (id, email, name, password_hash, verified, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user.id, email, name, hash_password(password), verified, time.time()),
        )
        if not verified:
            self.send_verification(user)
        return user

    def check_credentials(self, email: str, password: str) -> dict:
        row = self.db.one("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
        valid = verify_password(password, row["password_hash"] if row else DUMMY_HASH)
        if not row or not valid:
            raise UserError("The email or password is incorrect.", "invalid_credentials", 401)
        if not row["verified"]:
            raise UserError(
                "Please confirm your email address first. Check your inbox for the link, or request a new one.", "email_not_verified", 403
            )
        return row

    def start_session(self, row: dict) -> tuple[str, User]:
        token = secrets.token_urlsafe(32)
        expires = time.time() + self.settings.token_ttl_days * 86400
        self.db.run("INSERT INTO auth_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)", (hash_token(token), row["id"], expires))
        self.db.run("DELETE FROM auth_tokens WHERE expires_at < ?", (time.time(),))
        return token, User(id=row["id"], email=row["email"], name=row["name"])

    def login(self, email: str, password: str) -> tuple[str, User]:
        row = self.check_credentials(email, password)
        if row["totp_enabled"]:
            raise UserError("Enter the code from your authenticator app.", "two_factor_required", 401)
        return self.start_session(row)

    def begin_login(self, email: str, password: str) -> tuple[str | None, User, str | None]:
        row = self.check_credentials(email, password)
        if not row["totp_enabled"]:
            token, user = self.start_session(row)
            return token, user, None
        challenge = self.issue_email_token(row["id"], "2fa", CHALLENGE_SECONDS)
        return None, User(id=row["id"], email=row["email"], name=row["name"]), challenge

    def challenge_user_id(self, challenge: str) -> str | None:
        row = self.db.one("SELECT user_id FROM email_tokens WHERE token_hash = ? AND purpose = '2fa'", (hash_token(challenge),))
        return row["user_id"] if row else None

    def finish_login(self, challenge: str, code: str) -> tuple[str, User]:
        row = self.db.one(
            "SELECT u.* FROM email_tokens t JOIN users u ON u.id = t.user_id WHERE t.token_hash = ? AND t.purpose = '2fa' AND t.expires_at > ?",
            (hash_token(challenge), time.time()),
        )
        if row is None or not row["totp_enabled"]:
            raise UserError("This sign-in has expired. Enter your password again.", "challenge_expired", 401)
        if not self.accept_code(row, code):
            raise UserError("That code is not correct.", "invalid_code", 401)
        self.db.run("DELETE FROM email_tokens WHERE token_hash = ?", (hash_token(challenge),))
        return self.start_session(row)

    def accept_code(self, row: dict, code: str) -> bool:
        secret = self.box.open(row["totp_secret"].encode())
        step = twofactor.verify_code(secret, code, row["totp_last_step"])
        if step is not None:
            return self.db.run("UPDATE users SET totp_last_step = ? WHERE id = ? AND totp_last_step < ?", (step, row["id"], step)) == 1
        return self.db.run(
            "DELETE FROM recovery_codes WHERE code_hash = ? AND user_id = ?", (twofactor.hash_recovery_code(code), row["id"])
        ) == 1

    def require_two_factor(self) -> None:
        if not self.two_factor_available():
            raise UserError("Two-factor sign-in needs SECRET_KEY to be set on this server.", "two_factor_unavailable", 501)

    def two_factor_status(self, user: User) -> dict:
        row = self.db.one("SELECT totp_enabled FROM users WHERE id = ?", (user.id,))
        remaining = self.db.one("SELECT count(*) AS n FROM recovery_codes WHERE user_id = ?", (user.id,))["n"]
        return {"available": self.two_factor_available(), "enabled": bool(row and row["totp_enabled"]), "recovery_remaining": remaining}

    def check_password_of(self, user: User, password: str) -> dict:
        row = self.db.one("SELECT * FROM users WHERE id = ?", (user.id,))
        if row is None or not verify_password(password, row["password_hash"]):
            raise UserError("The password is incorrect.", "invalid_credentials", 403)
        return row

    def start_two_factor(self, user: User, password: str) -> dict:
        self.require_two_factor()
        row = self.check_password_of(user, password)
        if row["totp_enabled"]:
            raise UserError("Two-factor sign-in is already on.", "two_factor_enabled", 409)
        secret = twofactor.new_secret()
        self.db.run("UPDATE users SET totp_secret = ?, totp_last_step = 0 WHERE id = ?", (self.box.seal(secret).decode(), user.id))
        uri = twofactor.otpauth_uri(secret, user.email)
        return {"secret": secret, "uri": uri, "qr_svg": twofactor.qr_svg(uri)}

    def enable_two_factor(self, user: User, code: str, token: str) -> list[str]:
        self.require_two_factor()
        row = self.db.one("SELECT * FROM users WHERE id = ?", (user.id,))
        if row is None or row["totp_enabled"] or not row["totp_secret"]:
            raise UserError("Start the setup first.", "two_factor_not_started", 409)
        step = twofactor.verify_code(self.box.open(row["totp_secret"].encode()), code)
        if step is None:
            raise UserError("That code is not correct. Check the time on your phone and try again.", "invalid_code", 422)
        codes = twofactor.new_recovery_codes()
        self.db.run("DELETE FROM recovery_codes WHERE user_id = ?", (user.id,))
        for item in codes:
            self.db.run("INSERT INTO recovery_codes (code_hash, user_id) VALUES (?, ?)", (twofactor.hash_recovery_code(item), user.id))
        self.db.run("UPDATE users SET totp_enabled = 1, totp_last_step = ? WHERE id = ?", (step, user.id))
        self.db.run("DELETE FROM auth_tokens WHERE user_id = ? AND token_hash <> ?", (user.id, hash_token(token)))
        self.notify_two_factor(row, "turned on")
        return codes

    def disable_two_factor(self, user: User, password: str, code: str) -> None:
        row = self.check_password_of(user, password)
        if not row["totp_enabled"]:
            raise UserError("Two-factor sign-in is not on.", "two_factor_disabled", 409)
        if not self.accept_code(row, code):
            raise UserError("That code is not correct.", "invalid_code", 401)
        self.clear_two_factor(user.id)
        self.notify_two_factor(row, "turned off")

    def clear_two_factor(self, user_id: str) -> None:
        self.db.run("UPDATE users SET totp_secret = NULL, totp_enabled = 0, totp_last_step = 0 WHERE id = ?", (user_id,))
        self.db.run("DELETE FROM recovery_codes WHERE user_id = ?", (user_id,))

    def notify_two_factor(self, row: dict, action: str) -> None:
        self.mailer.send(
            row["email"], f"Two-factor sign-in {action} for DataPilot",
            compose(
                f"Hi {row['name']},",
                "",
                f"Two-factor sign-in was just {action} on your DataPilot account.",
                "If this was not you, reset your password immediately.",
            ),
        )

    def sign_in_with_sso(self, email: str, name: str) -> tuple[str, User]:
        if not EMAIL_PATTERN.match(email):
            raise UserError("The identity provider returned an invalid email address.", "invalid_email", 422)
        domain = self.settings.allowed_email_domain.strip().lower()
        if domain and not email.endswith("@" + domain):
            raise UserError(f"Only {domain} email addresses can sign in to this server.", "email_domain_not_allowed", 403)
        row = self.db.one("SELECT * FROM users WHERE email = ?", (email,))
        if row is None:
            if self.settings.registration != "open":
                raise UserError("Registration is closed on this server.", "registration_closed", 403)
            user_id = uuid.uuid4().hex
            self.db.run(
                "INSERT INTO users (id, email, name, password_hash, verified, created_at) VALUES (?, ?, ?, ?, 1, ?)",
                (user_id, email, name, hash_password(secrets.token_urlsafe(32)), time.time()),
            )
        else:
            self.db.run("UPDATE users SET verified = 1 WHERE id = ? AND verified = 0", (row["id"],))
        return self.start_session(self.db.one("SELECT * FROM users WHERE email = ?", (email,)))

    def user_for_token(self, token: str) -> User | None:
        row = self.db.one(
            "SELECT u.id, u.email, u.name FROM auth_tokens t JOIN users u ON u.id = t.user_id WHERE t.token_hash = ? AND t.expires_at > ?",
            (hash_token(token), time.time()),
        )
        return User(**row) if row else None

    def logout(self, token: str) -> None:
        self.db.run("DELETE FROM auth_tokens WHERE token_hash = ?", (hash_token(token),))

    def role_in_team(self, user_id: str, team_id: str) -> str | None:
        row = self.db.one("SELECT role FROM memberships WHERE team_id = ? AND user_id = ?", (team_id, user_id))
        return row["role"] if row else None

    def create_team(self, user: User, name: str) -> Team:
        name = name.strip()
        if not 1 <= len(name) <= 80:
            raise UserError("Enter a team name of up to 80 characters.", "invalid_name", 422)
        owned = self.db.one("SELECT count(*) AS n FROM teams WHERE owner_id = ?", (user.id,))["n"]
        if owned >= self.settings.max_teams_per_user:
            raise UserError("You have reached the team limit.", "too_many_teams", 422)
        team = Team(id=uuid.uuid4().hex, name=name, role="admin")
        self.db.run("INSERT INTO teams (id, name, owner_id, created_at) VALUES (?, ?, ?, ?)", (team.id, name, user.id, time.time()))
        self.db.run("INSERT INTO memberships (team_id, user_id, role) VALUES (?, ?, 'admin')", (team.id, user.id))
        return team

    def teams_for(self, user: User) -> list[Team]:
        rows = self.db.all(
            "SELECT t.id, t.name, m.role FROM memberships m JOIN teams t ON t.id = m.team_id WHERE m.user_id = ? ORDER BY t.name",
            (user.id,),
        )
        return [Team(**row) for row in rows]

    def require_member(self, user: User, team_id: str) -> str:
        role = self.role_in_team(user.id, team_id)
        if role is None:
            raise UserError("Team not found.", "team_not_found", 404)
        return role

    def members(self, user: User, team_id: str) -> list[Member]:
        self.require_member(user, team_id)
        rows = self.db.all(
            "SELECT u.id AS user_id, u.email, u.name, m.role FROM memberships m JOIN users u ON u.id = m.user_id WHERE m.team_id = ? ORDER BY u.name",
            (team_id,),
        )
        return [Member(**row) for row in rows]

    def add_member(self, actor: User, team_id: str, email: str, role: str) -> Member:
        if self.require_member(actor, team_id) != "admin":
            raise UserError("Only team admins can add members.", "forbidden", 403)
        if role not in TEAM_ROLES:
            raise UserError("Role must be admin, member or viewer.", "invalid_role", 422)
        target = self.db.one("SELECT id, email, name FROM users WHERE email = ?", (email.strip().lower(),))
        if target is None:
            raise UserError("No account exists for that email. Ask them to register first.", "user_not_found", 404)
        self.db.run("INSERT OR REPLACE INTO memberships (team_id, user_id, role) VALUES (?, ?, ?)", (team_id, target["id"], role))
        return Member(user_id=target["id"], email=target["email"], name=target["name"], role=role)

    def remove_member(self, actor: User, team_id: str, user_id: str) -> None:
        role = self.require_member(actor, team_id)
        if role != "admin" and actor.id != user_id:
            raise UserError("Only team admins can remove other members.", "forbidden", 403)
        admins = self.db.one("SELECT count(*) AS n FROM memberships WHERE team_id = ? AND role = 'admin'", (team_id,))["n"]
        if self.role_in_team(user_id, team_id) == "admin" and admins <= 1:
            raise UserError("A team needs at least one admin.", "last_admin", 422)
        self.db.run("DELETE FROM memberships WHERE team_id = ? AND user_id = ?", (team_id, user_id))
        self.db.run("UPDATE workspaces SET team_id = NULL WHERE team_id = ? AND owner_id = ?", (team_id, user_id))

    def register_workspace(self, session_id: str, owner_id: str | None, name: str) -> None:
        now = time.time()
        self.db.run(
            "INSERT OR IGNORE INTO workspaces (session_id, owner_id, team_id, name, created_at, updated_at) VALUES (?, ?, NULL, ?, ?, ?)",
            (session_id, owner_id, name, now, now),
        )

    def workspace(self, session_id: str) -> dict | None:
        return self.db.one("SELECT * FROM workspaces WHERE session_id = ?", (session_id,))

    def access(self, session_id: str, user: User) -> str | None:
        row = self.workspace(session_id)
        if row is None:
            return None
        if row["owner_id"] == user.id:
            return "owner"
        if row["team_id"]:
            role = self.role_in_team(user.id, row["team_id"])
            if role in ("admin", "member"):
                return "writer"
            if role == "viewer":
                return "reader"
        return None

    def workspaces_for(self, user: User) -> list[dict]:
        return self.db.all(
            "SELECT w.session_id, w.name, w.team_id, w.owner_id, w.updated_at, t.name AS team_name FROM workspaces w "
            "LEFT JOIN teams t ON t.id = w.team_id "
            "WHERE w.owner_id = ? OR w.team_id IN (SELECT team_id FROM memberships WHERE user_id = ?) ORDER BY w.updated_at DESC",
            (user.id, user.id),
        )

    def rename_workspace(self, session_id: str, name: str) -> None:
        name = name.strip()
        if not 1 <= len(name) <= 80:
            raise UserError("Enter a name of up to 80 characters.", "invalid_name", 422)
        self.db.run("UPDATE workspaces SET name = ?, updated_at = ? WHERE session_id = ?", (name, time.time(), session_id))

    def set_team(self, session_id: str, user: User | None, team_id: str | None) -> None:
        if team_id is not None:
            if user is None or self.role_in_team(user.id, team_id) not in ("admin", "member"):
                raise UserError("You can only move a workspace into a team where you can edit.", "forbidden", 403)
        self.db.run("UPDATE workspaces SET team_id = ?, updated_at = ? WHERE session_id = ?", (team_id, time.time(), session_id))

    def touch_workspace(self, session_id: str) -> None:
        self.db.run("UPDATE workspaces SET updated_at = ? WHERE session_id = ?", (time.time(), session_id))

    def delete_workspace(self, session_id: str) -> None:
        self.db.run("DELETE FROM workspaces WHERE session_id = ?", (session_id,))
        run_ids = self.db.all("SELECT id FROM schedules WHERE session_id = ?", (session_id,))
        for row in run_ids:
            self.db.run("DELETE FROM schedule_runs WHERE schedule_id = ?", (row["id"],))
        self.db.run("DELETE FROM schedules WHERE session_id = ?", (session_id,))

    def has_schedules(self, session_id: str) -> bool:
        return self.db.one("SELECT 1 AS found FROM schedules WHERE session_id = ? AND enabled = 1", (session_id,)) is not None

    def issue_email_token(self, user_id: str, purpose: str, ttl_seconds: float) -> str:
        token = secrets.token_urlsafe(32)
        self.db.run("DELETE FROM email_tokens WHERE user_id = ? AND purpose = ?", (user_id, purpose))
        self.db.run("DELETE FROM email_tokens WHERE expires_at < ?", (time.time(),))
        self.db.run(
            "INSERT INTO email_tokens (token_hash, user_id, purpose, expires_at) VALUES (?, ?, ?, ?)",
            (hash_token(token), user_id, purpose, time.time() + ttl_seconds),
        )
        return token

    def take_email_token(self, token: str, purpose: str) -> str:
        digest = hash_token(token)
        row = self.db.one("SELECT user_id FROM email_tokens WHERE token_hash = ? AND purpose = ? AND expires_at > ?", (digest, purpose, time.time()))
        if row is None:
            raise UserError("This link is invalid or has expired. Request a new one.", "invalid_link", 400)
        if self.db.run("DELETE FROM email_tokens WHERE token_hash = ?", (digest,)) == 0:
            raise UserError("This link is invalid or has expired. Request a new one.", "invalid_link", 400)
        return row["user_id"]

    def link(self, path: str, token: str) -> str:
        return f"{self.settings.public_url.rstrip('/')}/{path}?token={token}"

    def send_verification(self, user: User) -> None:
        token = self.issue_email_token(user.id, "verify", self.settings.verify_token_hours * 3600)
        self.mailer.send(
            user.email, "Confirm your DataPilot email",
            compose(
                f"Hi {user.name},",
                "",
                "Confirm your email address to finish creating your DataPilot account:",
                self.link("verify", token),
                "",
                f"The link works once and expires in {self.settings.verify_token_hours} hours. If you did not sign up, ignore this message.",
            ),
        )

    def verify_email(self, token: str) -> None:
        user_id = self.take_email_token(token, "verify")
        self.db.run("UPDATE users SET verified = 1 WHERE id = ?", (user_id,))

    def resend_verification(self, email: str) -> None:
        row = self.db.one("SELECT id, email, name, verified FROM users WHERE email = ?", (email.strip().lower(),))
        if row and not row["verified"] and self.needs_verification():
            self.send_verification(User(id=row["id"], email=row["email"], name=row["name"]))

    def forgot_password(self, email: str) -> None:
        row = self.db.one("SELECT id, email, name FROM users WHERE email = ?", (email.strip().lower(),))
        if row is None or not self.mailer.enabled:
            return
        token = self.issue_email_token(row["id"], "reset", self.settings.reset_token_minutes * 60)
        self.mailer.send(
            row["email"], "Reset your DataPilot password",
            compose(
                f"Hi {row['name']},",
                "",
                "Someone asked to reset the password for this account. To choose a new one, open:",
                self.link("reset", token),
                "",
                f"The link works once and expires in {self.settings.reset_token_minutes} minutes. "
                "If this was not you, ignore this message; your password has not changed.",
            ),
        )

    def check_new_password(self, password: str) -> None:
        if not 10 <= len(password) <= 200:
            raise UserError("Choose a password between 10 and 200 characters.", "weak_password", 422)

    def set_password(self, user_id: str, password: str, keep_token: str | None = None) -> None:
        self.db.run("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user_id))
        if keep_token:
            self.db.run("DELETE FROM auth_tokens WHERE user_id = ? AND token_hash <> ?", (user_id, hash_token(keep_token)))
        else:
            self.db.run("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
        row = self.db.one("SELECT email, name FROM users WHERE id = ?", (user_id,))
        if row:
            self.mailer.send(
                row["email"], "Your DataPilot password was changed",
                compose(
                    f"Hi {row['name']},",
                    "",
                    "The password for your DataPilot account was just changed and other sessions were signed out.",
                    "If this was not you, reset your password immediately.",
                ),
            )

    def reset_password(self, token: str, password: str) -> None:
        self.check_new_password(password)
        user_id = self.take_email_token(token, "reset")
        self.db.run("UPDATE users SET verified = 1 WHERE id = ? AND verified = 0", (user_id,))
        self.set_password(user_id, password)

    def change_password(self, user: User, current: str, new: str, token: str) -> None:
        row = self.db.one("SELECT password_hash FROM users WHERE id = ?", (user.id,))
        if row is None or not verify_password(current, row["password_hash"]):
            raise UserError("The current password is incorrect.", "invalid_credentials", 403)
        self.check_new_password(new)
        self.set_password(user.id, new, keep_token=token)
