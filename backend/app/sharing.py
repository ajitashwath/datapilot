import json
import secrets
import time

from app.config import Settings
from app.db import Database
from app.errors import UserError
from app.session import Session

MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024


class Sharing:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings

    def create(self, session: Session, title: str, user_id: str | None) -> dict:
        if not session.transcript:
            raise UserError("Ask at least one question before sharing, so there is something to show.", "nothing_to_share", 422)
        active = self.db.one("SELECT count(*) AS n FROM shares WHERE session_id = ? AND revoked = 0", (session.id,))["n"]
        if active >= self.settings.max_shares_per_session:
            raise UserError("This workspace has reached its share link limit. Revoke one first.", "too_many_shares", 422)
        title = title.strip() or "Shared analysis"
        snapshot = {
            "title": title,
            "created_at": time.time(),
            "datasets": [{"name": p.name, "rows": p.rows, "columns": p.column_count} for p in session.store.profiles.values()],
            "transcript": session.transcript,
        }
        payload = json.dumps(snapshot)
        if len(payload) > MAX_SNAPSHOT_BYTES:
            raise UserError("This conversation is too large to share. Clear some of it and try again.", "snapshot_too_large", 422)
        token = secrets.token_urlsafe(16)
        self.db.run(
            "INSERT INTO shares (token, session_id, title, created_by, created_at, snapshot) VALUES (?, ?, ?, ?, ?, ?)",
            (token, session.id, title, user_id, snapshot["created_at"], payload),
        )
        return {"token": token, "title": title, "created_at": snapshot["created_at"], "revoked": False}

    def for_session(self, session_id: str) -> list[dict]:
        rows = self.db.all("SELECT token, title, created_at, revoked FROM shares WHERE session_id = ? ORDER BY created_at DESC", (session_id,))
        return [{**row, "revoked": bool(row["revoked"])} for row in rows]

    def revoke(self, session_id: str, token: str) -> None:
        if self.db.run("UPDATE shares SET revoked = 1 WHERE token = ? AND session_id = ?", (token, session_id)) == 0:
            raise UserError("Share link not found.", "share_not_found", 404)

    def snapshot(self, token: str) -> dict:
        row = self.db.one("SELECT snapshot FROM shares WHERE token = ? AND revoked = 0", (token,))
        if row is None:
            raise UserError("This share link does not exist or has been revoked.", "share_not_found", 404)
        return json.loads(row["snapshot"])
