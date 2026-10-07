import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 1,
    totp_secret TEXT,
    totp_enabled INTEGER NOT NULL DEFAULT 0,
    totp_last_step INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS recovery_codes (
    code_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS email_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sso_states (
    state_hash TEXT PRIMARY KEY,
    nonce TEXT NOT NULL,
    verifier TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships (
    team_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    PRIMARY KEY (team_id, user_id)
);
CREATE TABLE IF NOT EXISTS workspaces (
    session_id TEXT PRIMARY KEY,
    owner_id TEXT,
    team_id TEXT,
    name TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS shares (
    token TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_by TEXT,
    created_at REAL NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    snapshot TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    name TEXT NOT NULL,
    sql TEXT NOT NULL,
    every_minutes INTEGER NOT NULL,
    refresh_sources INTEGER NOT NULL DEFAULT 0,
    notify TEXT NOT NULL DEFAULT 'none',
    webhook_url TEXT,
    webhook_secret TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    next_run_at REAL NOT NULL,
    created_by TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS schedule_runs (
    id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL,
    ran_at REAL NOT NULL,
    ok INTEGER NOT NULL,
    error TEXT,
    columns TEXT,
    rows TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_schedule ON schedule_runs (schedule_id, ran_at);
CREATE INDEX IF NOT EXISTS idx_shares_session ON shares (session_id);
CREATE INDEX IF NOT EXISTS idx_schedules_session ON schedules (session_id);
"""


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(SCHEMA)
        self.add_missing_columns()

    def add_missing_columns(self) -> None:
        wanted = {
            "users": [
                ("verified", "INTEGER NOT NULL DEFAULT 1"),
                ("totp_secret", "TEXT"),
                ("totp_enabled", "INTEGER NOT NULL DEFAULT 0"),
                ("totp_last_step", "INTEGER NOT NULL DEFAULT 0"),
            ],
            "schedules": [("notify", "TEXT NOT NULL DEFAULT 'none'"), ("webhook_url", "TEXT"), ("webhook_secret", "TEXT")],
        }
        for table, columns in wanted.items():
            existing = {row[1] for row in self.con.execute(f"PRAGMA table_info({table})")}
            for name, definition in columns:
                if name not in existing:
                    self.con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def run(self, sql: str, params: tuple = ()) -> int:
        with self.lock:
            return self.con.execute(sql, params).rowcount

    def all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(row) for row in self.con.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def close(self) -> None:
        with self.lock:
            self.con.close()
