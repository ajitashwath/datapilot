import json
import threading
import time
import uuid

import httpx

from app.config import Settings
from app.connectors import refresh_sources
from app.data.engine import validate_select
from app.db import Database
from app.errors import UserError
from app.logging_setup import log_event
from app.metrics import metrics
from app.session import Session, SessionManager

STORED_ROWS = 50
RETRY_WHEN_BUSY_SECONDS = 60


class Schedules:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings

    def create(self, session: Session, name: str, sql: str, every_minutes: int, refresh: bool, user_id: str | None) -> dict:
        name = name.strip()
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
            "INSERT INTO schedules (id, session_id, name, sql, every_minutes, refresh_sources, enabled, next_run_at, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (schedule_id, session.id, name, sql, every_minutes, int(refresh), now + every_minutes * 60, user_id, now),
        )
        return self.get(session.id, schedule_id)

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
            "refresh_sources": bool(row["refresh_sources"]), "enabled": bool(row["enabled"]), "next_run_at": row["next_run_at"],
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
    except UserError as exc:
        error = exc.message
    except Exception:
        log_event("schedule_failed", schedule=row["id"], exc_info=True)
        error = "The scheduled query failed unexpectedly."
    finally:
        session.lock.release()
    schedules.record(row["id"], error is None, error, columns, rows, row_count, note)
    schedules.advance(row)
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
