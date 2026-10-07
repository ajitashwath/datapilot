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

EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
TEAM_ROLES = {"admin", "member", "viewer"}
SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
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


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Accounts:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings

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
        self.db.run(
            "INSERT INTO users (id, email, name, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (user.id, email, name, hash_password(password), time.time()),
        )
        return user

    def login(self, email: str, password: str) -> tuple[str, User]:
        row = self.db.one("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
        valid = verify_password(password, row["password_hash"] if row else DUMMY_HASH)
        if not row or not valid:
            raise UserError("The email or password is incorrect.", "invalid_credentials", 401)
        token = secrets.token_urlsafe(32)
        expires = time.time() + self.settings.token_ttl_days * 86400
        self.db.run("INSERT INTO auth_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)", (hash_token(token), row["id"], expires))
        self.db.run("DELETE FROM auth_tokens WHERE expires_at < ?", (time.time(),))
        return token, User(id=row["id"], email=row["email"], name=row["name"])

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
