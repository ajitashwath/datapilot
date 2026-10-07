import hashlib
import hmac
import json
import secrets
import threading
import time
import uuid

import httpx

from app.config import Settings
from app.connectors import normalise_url, pinned_request, public_addresses, refresh_sources
from urllib.parse import urlparse
from app.data.engine import validate_select
from app.db import Database
from app.errors import UserError
from app.logging_setup import log_event
from app.mailer import Mailer
from app.metrics import metrics
from app.session import Session, SessionManager

STORED_ROWS = 50
RETRY_WHEN_BUSY_SECONDS = 60


class Schedules:
    def __init__(self, db: Database, settings: Settings, mailer: Mailer):
        self.db = db
        self.settings = settings
        self.mailer = mailer

    def create(
        self, session: Session, name: str, sql: str, every_minutes: int, refresh: bool, user_id: str | None, notify: str = 'none',
        webhook_url: str | None = None,
    ) -> dict:
        name = name.strip()
        if notify not in ('none', 'failure', 'always'):
            raise UserError('Notify must be none, failure or always.', 'invalid_notify', 422)
        webhook_url = (webhook_url or '').strip() or None
        if webhook_url:
            webhook_url = normalise_url(webhook_url, self.settings.allow_private_connections)
            public_addresses(urlparse(webhook_url).hostname, urlparse(webhook_url).port or 443, self.settings.allow_private_connections)
        if notify != 'none' and not self.mailer.enabled and not webhook_url:
            raise UserError('Email is not set up on this server, so notifications are unavailable.', 'email_disabled', 501)
        if webhook_url and notify == 'none':
            raise UserError('Choose when to notify, or remove the webhook address.', 'invalid_notify', 422)
        webhook_secret = secrets.token_urlsafe(24) if webhook_url else None
        if not 1 <= len(name) <= 80:
            raise UserError("Enter a name of up to 80 characters.", "invalid_name", 422)
        if every_minutes < self.settings.schedule_min_minutes:
            raise UserError(f"Schedules must run at least {self.settings.schedule_min_minutes} minutes apart.", "interval_too_short", 422)
        if every_minutes > 60 * 24 * 31:
            raise UserError("Schedules can repeat at most every 31 days.", "interval_too_long", 422)
        count = self.db.one("SELECT count(*) AS n FROM schedules WHERE session_id = ?", (session.id,))["n"]
        if count >= self.settings.max_schedules_per_session:
            raise UserError("This workspace has reached its schedule limit.", "too_many_schedules", 422)
        sql = validate_select(session.store.con, sql, session.store.table_names())
        schedule_id = uuid.uuid4().hex
        now = time.time()
        self.db.run(
            "INSERT INTO schedules (id, session_id, name, sql, every_minutes, refresh_sources, notify, webhook_url, webhook_secret, enabled, "
            "next_run_at, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (schedule_id, session.id, name, sql, every_minutes, int(refresh), notify, webhook_url, webhook_secret, now + every_minutes * 60, user_id, now),
        )
        created = self.get(session.id, schedule_id)
        if webhook_secret:
            created["webhook_secret"] = webhook_secret
        return created

    def get(self, session_id: str, schedule_id: str) -> dict:
        row = self.db.one("SELECT * FROM schedules WHERE id = ? AND session_id = ?", (schedule_id, session_id))
        if row is None:
            raise UserError("Schedule not found.", "schedule_not_found", 404)
        return self.describe(row)

    def describe(self, row: dict) -> dict:
        last = self.db.one(
            "SELECT id, ran_at, ok, error, row_count, note FROM schedule_runs WHERE schedule_id = ? ORDER BY ran_at DESC LIMIT 1", (row["id"],)
        )
        return {
            "id": row["id"], "name": row["name"], "sql": row["sql"], "every_minutes": row["every_minutes"],
            "refresh_sources": bool(row["refresh_sources"]), "notify": row["notify"], "webhook_host": urlparse(row["webhook_url"]).netloc if row["webhook_url"] else None, "enabled": bool(row["enabled"]), "next_run_at": row["next_run_at"],
            "last_run": {**last, "ok": bool(last["ok"])} if last else None,
        }

    def for_session(self, session_id: str) -> list[dict]:
        rows = self.db.all("SELECT * FROM schedules WHERE session_id = ? ORDER BY created_at", (session_id,))
        return [self.describe(row) for row in rows]

    def set_enabled(self, session_id: str, schedule_id: str, enabled: bool) -> dict:
        self.get(session_id, schedule_id)
        next_run = time.time() + self.db.one("SELECT every_minutes FROM schedules WHERE id = ?", (schedule_id,))["every_minutes"] * 60
        self.db.run("UPDATE schedules SET enabled = ?, next_run_at = ? WHERE id = ?", (int(enabled), next_run, schedule_id))
        return self.get(session_id, schedule_id)

    def delete(self, session_id: str, schedule_id: str) -> None:
        self.get(session_id, schedule_id)
        self.db.run("DELETE FROM schedule_runs WHERE schedule_id = ?", (schedule_id,))
        self.db.run("DELETE FROM schedules WHERE id = ?", (schedule_id,))

    def runs(self, session_id: str, schedule_id: str, limit: int = 10) -> list[dict]:
        self.get(session_id, schedule_id)
        rows = self.db.all(
            "SELECT id, ran_at, ok, error, columns, rows, row_count, note FROM schedule_runs WHERE schedule_id = ? ORDER BY ran_at DESC LIMIT ?",
            (schedule_id, limit),
        )
        return [
            {**row, "ok": bool(row["ok"]), "columns": json.loads(row["columns"] or "[]"), "rows": json.loads(row["rows"] or "[]")}
            for row in rows
        ]

    def record(self, schedule_id: str, ok: bool, error: str | None, columns: list, rows: list, row_count: int, note: str) -> None:
        self.db.run(
            "INSERT INTO schedule_runs (id, schedule_id, ran_at, ok, error, columns, rows, row_count, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, schedule_id, time.time(), int(ok), error, json.dumps(columns), json.dumps(rows), row_count, note),
        )
        self.db.run(
            "DELETE FROM schedule_runs WHERE schedule_id = ? AND id NOT IN "
            "(SELECT id FROM schedule_runs WHERE schedule_id = ? ORDER BY ran_at DESC LIMIT ?)",
            (schedule_id, schedule_id, self.settings.schedule_runs_kept),
        )

    def wants_notice(self, row: dict, ok: bool) -> bool:
        return row["notify"] == "always" or (row["notify"] == "failure" and not ok)

    def send_webhook(self, row: dict, ok: bool, error: str | None, row_count: int, transport: httpx.BaseTransport | None = None) -> str:
        if not row["webhook_url"] or not self.wants_notice(row, ok):
            return ""
        payload = {
            "event": "schedule.run", "schedule_id": row["id"], "schedule": row["name"], "workspace": row["session_id"],
            "ok": ok, "row_count": row_count, "error": error, "ran_at": time.time(),
        }
        body = json.dumps(payload, separators=(",", ":")).encode()
        signature = hmac.new((row["webhook_secret"] or "").encode(), body, hashlib.sha256).hexdigest()
        try:
            target, headers, extensions = pinned_request(row["webhook_url"], self.settings.allow_private_connections)
            headers.update({"Accept": "*/*", "Content-Type": "application/json", "X-DataPilot-Signature": f"sha256={signature}"})
            with httpx.Client(transport=transport, timeout=self.settings.connector_timeout_seconds, follow_redirects=False) as client:
                response = client.post(target, content=body, headers=headers, extensions=extensions)
            delivered = 200 <= response.status_code < 300
            outcome = "Webhook delivered." if delivered else f"Webhook failed with status {response.status_code}."
        except UserError as exc:
            delivered, outcome = False, f"Webhook not sent: {exc.message}"
        except httpx.HTTPError:
            delivered, outcome = False, "Webhook failed: the server could not be reached."
        metrics.inc("datapilot_webhooks_total", ok=str(delivered).lower())
        return outcome

    def notify_owner(self, row: dict, ok: bool, error: str | None, row_count: int) -> None:
        if not self.wants_notice(row, ok) or not row["created_by"]:
            return
        owner = self.db.one("SELECT email, name FROM users WHERE id = ?", (row["created_by"],))
        if owner is None:
            return
        status = "ran successfully" if ok else "failed"
        detail = f"It returned {row_count} row{'s' if row_count != 1 else ''}." if ok else f"Reason: {error}"
        lines = [
            f"Hi {owner['name']},",
            "",
            f'Your scheduled query "{row["name"]}" {status}.',
            detail,
            "",
            f"Open DataPilot to see the results: {self.settings.public_url.rstrip('/')}",
            "",
            "No data is included in this email on purpose.",
        ]
        self.mailer.send(owner["email"], f"DataPilot schedule {status}: {row['name']}", "\n".join(lines) + "\n")

    def due(self, now: float) -> list[dict]:
        return self.db.all("SELECT * FROM schedules WHERE enabled = 1 AND next_run_at <= ?", (now,))

    def postpone(self, schedule_id: str, seconds: float) -> None:
        self.db.run("UPDATE schedules SET next_run_at = ? WHERE id = ?", (time.time() + seconds, schedule_id))

    def advance(self, row: dict) -> None:
        self.db.run("UPDATE schedules SET next_run_at = ? WHERE id = ?", (time.time() + row["every_minutes"] * 60, row["id"]))


def execute_schedule(
    schedules: Schedules, manager: SessionManager, settings: Settings, row: dict, transport: httpx.BaseTransport | None = None
) -> dict:
    try:
        session = manager.get(row["session_id"])
    except UserError:
        schedules.delete(row["session_id"], row["id"])
        raise
    if not session.lock.acquire(blocking=False):
        schedules.postpone(row["id"], RETRY_WHEN_BUSY_SECONDS)
        return {"skipped": True}
    started = time.perf_counter()
    note, columns, rows, row_count, error = "", [], [], 0, None
    try:
        if row["refresh_sources"]:
            note = refresh_sources(session, settings, transport)
        table = session.store.query(row["sql"], max_rows=STORED_ROWS)
        columns, rows, row_count = table.columns, table.rows, table.row_count
        if table.truncated:
            row_count = session.store.query(f"SELECT count(*) AS n FROM ({row['sql']})", max_rows=1).rows[0][0]
    except UserError as exc:
        error = exc.message
    except Exception:
        log_event("schedule_failed", schedule=row["id"], exc_info=True)
        error = "The scheduled query failed unexpectedly."
    finally:
        session.lock.release()
    hook = schedules.send_webhook(row, error is None, error, row_count, transport)
    note = f"{note} {hook}".strip()
    schedules.record(row["id"], error is None, error, columns, rows, row_count, note)
    schedules.advance(row)
    schedules.notify_owner(row, error is None, error, row_count)
    metrics.inc("datapilot_schedule_runs_total", ok=str(error is None).lower())
    log_event("schedule_ran", schedule=row["id"], ok=error is None, duration_ms=round((time.perf_counter() - started) * 1000, 1))
    return {"skipped": False, "ok": error is None}


class Scheduler(threading.Thread):
    def __init__(self, schedules: Schedules, manager: SessionManager, settings: Settings, tick_seconds: float = 30.0):
        super().__init__(daemon=True, name="datapilot-scheduler")
        self.schedules = schedules
        self.manager = manager
        self.settings = settings
        self.tick_seconds = tick_seconds
        self.stopping = threading.Event()
        self.transport: httpx.BaseTransport | None = None

    def run_due(self, now: float | None = None) -> int:
        ran = 0
        for row in self.schedules.due(now if now is not None else time.time()):
            try:
                result = execute_schedule(self.schedules, self.manager, self.settings, row, self.transport)
                ran += 0 if result["skipped"] else 1
            except UserError:
                continue
            except Exception:
                log_event("scheduler_error", schedule=row["id"], exc_info=True)
        return ran

    def run(self) -> None:
        while not self.stopping.wait(self.tick_seconds):
            self.run_due()

    def stop(self) -> None:
        self.stopping.set()
