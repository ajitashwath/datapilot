from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import current_user, session_of
from app.api.security import require_token
from app.schedules import execute_schedule

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    sql: str = Field(min_length=1, max_length=8000)
    every_minutes: int = Field(ge=1)
    refresh_sources: bool = False


class ScheduleToggle(BaseModel):
    enabled: bool


@router.post("/sessions/{session_id}/schedules")
def create_schedule(request: Request, session_id: str, body: ScheduleCreate) -> dict:
    session = session_of(request, session_id)
    user = current_user(request)
    return request.app.state.schedules.create(
        session, body.name, body.sql, body.every_minutes, body.refresh_sources, user.id if user else None
    )


@router.get("/sessions/{session_id}/schedules")
def list_schedules(request: Request, session_id: str) -> list[dict]:
    session_of(request, session_id)
    return request.app.state.schedules.for_session(session_id)


@router.patch("/sessions/{session_id}/schedules/{schedule_id}")
def toggle_schedule(request: Request, session_id: str, schedule_id: str, body: ScheduleToggle) -> dict:
    session_of(request, session_id)
    return request.app.state.schedules.set_enabled(session_id, schedule_id, body.enabled)


@router.delete("/sessions/{session_id}/schedules/{schedule_id}")
def delete_schedule(request: Request, session_id: str, schedule_id: str) -> dict:
    session_of(request, session_id)
    request.app.state.schedules.delete(session_id, schedule_id)
    return {"deleted": True}


@router.get("/sessions/{session_id}/schedules/{schedule_id}/runs")
def schedule_runs(request: Request, session_id: str, schedule_id: str) -> list[dict]:
    session_of(request, session_id)
    return request.app.state.schedules.runs(session_id, schedule_id)


@router.post("/sessions/{session_id}/schedules/{schedule_id}/run")
def run_schedule_now(request: Request, session_id: str, schedule_id: str) -> dict:
    session_of(request, session_id)
    state = request.app.state
    schedules = state.schedules
    schedules.get(session_id, schedule_id)
    row = schedules.db.one("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
    execute_schedule(schedules, state.sessions, state.settings, row, state.http_transport)
    return {"run": schedules.runs(session_id, schedule_id, 1)[0], "schedule": schedules.get(session_id, schedule_id)}
