from collections.abc import Callable, Iterator
from pathlib import Path

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.agent import ErrorEvent, run_turn
from app.agent.llm import LLMError, LLMProvider
from app.api.schemas import (
    AppConfig, ChatRequest, DatasetDetail, RelationshipRequest, SessionCreated, SessionState, UploadError, UploadResponse,
)
from app.config import Settings
from app.data.overview import build_overview
from app.errors import UserError
from app.logging_setup import log_event, session_id_var
from app.models import QualityReport, Relationship, TableResult
from app.session import Session, SessionManager

router = APIRouter(prefix="/api")


def sessions_of(request: Request) -> SessionManager:
    return request.app.state.sessions


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


def session_of(request: Request, session_id: str) -> Session:
    session_id_var.set(session_id)
    return sessions_of(request).get(session_id)


def sample_files(settings: Settings) -> list[Path]:
    folder = Path(settings.sample_data_dir)
    return sorted(folder.glob("*.csv")) if folder.is_dir() else []


def detail_for(session: Session, name: str) -> DatasetDetail:
    quality = session.store.get_quality(name)
    return DatasetDetail(profile=session.store.get_profile(name), quality_score=quality.score, issue_count=len(quality.issues))


def state_of(session: Session) -> SessionState:
    return SessionState(
        session_id=session.id,
        datasets=[detail_for(session, name) for name in session.store.profiles],
        relationships=session.store.relationships,
        filters=session.filters,
        active_dataset=session.active_dataset,
    )


def sse(event: BaseModel) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/config")
def get_config(request: Request) -> AppConfig:
    s = settings_of(request)
    return AppConfig(
        llm_configured=bool(s.anthropic_api_key), model=s.llm_model, max_upload_mb=s.max_upload_mb,
        max_files_per_session=s.max_files_per_session, sql_timeout_seconds=s.sql_timeout_seconds,
        python_timeout_seconds=s.python_timeout_seconds, max_result_rows=s.max_result_rows,
        sample_datasets=[p.name for p in sample_files(s)],
    )


@router.post("/sessions")
def create_session(request: Request) -> SessionCreated:
    session = sessions_of(request).create()
    session_id_var.set(session.id)
    log_event("session_created")
    return SessionCreated(session_id=session.id)


@router.get("/sessions/{session_id}")
def get_session(request: Request, session_id: str) -> SessionState:
    return state_of(session_of(request, session_id))


@router.delete("/sessions/{session_id}")
def delete_session(request: Request, session_id: str) -> dict:
    session_of(request, session_id)
    sessions_of(request).delete(session_id)
    return {"deleted": True}


@router.post("/sessions/{session_id}/reset")
def reset_conversation(request: Request, session_id: str) -> SessionState:
    session = session_of(request, session_id)
    session.history, session.records, session.filters = [], [], {}
    return state_of(session)


@router.post("/sessions/{session_id}/datasets")
def upload_datasets(request: Request, session_id: str, files: list[UploadFile] = File(...)) -> UploadResponse:
    session = session_of(request, session_id)
    limit = settings_of(request).max_upload_mb * 1024 * 1024
    loaded, errors = [], []
    for file in files:
        name = file.filename or "unnamed"
        try:
            content = file.file.read(limit + 1)
            profile = session.store.add_csv(name, content)
            loaded.append(detail_for(session, profile.name))
            log_event("dataset_loaded", dataset=profile.name, rows=profile.rows, columns=profile.column_count)
        except UserError as exc:
            errors.append(UploadError(filename=name, message=exc.message))
            log_event("dataset_rejected", filename=name, reason=exc.code)
    return UploadResponse(datasets=loaded, errors=errors)


@router.post("/sessions/{session_id}/samples")
def load_samples(request: Request, session_id: str) -> UploadResponse:
    session = session_of(request, session_id)
    paths = sample_files(settings_of(request))
    if not paths:
        raise UserError("No sample datasets are available on this server.", "no_samples", 404)
    loaded, errors = [], []
    for path in paths:
        if path.stem in session.store.profiles:
            continue
        try:
            profile = session.store.add_csv(path.name, path.read_bytes())
            loaded.append(detail_for(session, profile.name))
        except UserError as exc:
            errors.append(UploadError(filename=path.name, message=exc.message))
    return UploadResponse(datasets=loaded, errors=errors)


@router.delete("/sessions/{session_id}/datasets/{name}")
def delete_dataset(request: Request, session_id: str, name: str) -> SessionState:
    session = session_of(request, session_id)
    session.store.remove(name)
    if session.active_dataset == name:
        session.active_dataset = None
    return state_of(session)


@router.get("/sessions/{session_id}/datasets/{name}/preview")
def preview_dataset(request: Request, session_id: str, name: str, limit: int = Query(50, ge=1, le=200)) -> TableResult:
    return session_of(request, session_id).store.preview(name, limit)


@router.get("/sessions/{session_id}/datasets/{name}/quality")
def dataset_quality(request: Request, session_id: str, name: str) -> QualityReport:
    return session_of(request, session_id).store.get_quality(name)


@router.get("/sessions/{session_id}/datasets/{name}/summary")
def dataset_summary(request: Request, session_id: str, name: str) -> dict:
    return build_overview(session_of(request, session_id).store, name)


@router.post("/sessions/{session_id}/relationships")
def add_relationship(request: Request, session_id: str, body: RelationshipRequest) -> Relationship:
    session = session_of(request, session_id)
    return session.store.add_relationship((body.left_table, body.left_column), (body.right_table, body.right_column))


@router.delete("/sessions/{session_id}/filters")
def clear_filters(request: Request, session_id: str) -> SessionState:
    session = session_of(request, session_id)
    session.filters = {}
    return state_of(session)


def event_stream(
    session: Session, body: ChatRequest, settings: Settings, llm_factory: Callable[[Settings], LLMProvider]
) -> Iterator[str]:
    session_id_var.set(session.id)
    if not session.lock.acquire(blocking=False):
        yield sse(ErrorEvent(message="Another question is still being answered in this session. Please wait for it to finish."))
        return
    try:
        if body.dataset and body.dataset in session.store.profiles:
            session.active_dataset = body.dataset
        if not session.store.profiles:
            yield sse(ErrorEvent(message="Upload a CSV file first, then ask a question about it."))
            return
        log_event("chat_started", question_chars=len(body.message))
        for event in run_turn(session, body.message, llm_factory(settings)):
            yield sse(event)
    except LLMError as exc:
        yield sse(ErrorEvent(message=exc.message))
    except Exception:
        log_event("chat_failed", exc_info=True)
        yield sse(ErrorEvent(message="Something went wrong while analysing your question. Please try again."))
    finally:
        session.lock.release()


@router.post("/sessions/{session_id}/chat")
def chat(request: Request, session_id: str, body: ChatRequest) -> StreamingResponse:
    session = session_of(request, session_id)
    stream = event_stream(session, body, settings_of(request), request.app.state.llm_factory)
    return StreamingResponse(
        stream, media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
