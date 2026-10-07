from collections.abc import Callable, Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from app.agent.agent import ErrorEvent, append_event, run_turn
from app.agent.llm import PROVIDER_DEFAULTS, LLMConfig, LLMError, LLMProvider, server_config
from app.api.schemas import (
    AppConfig, ChatRequest, DatasetDetail, LLMSettingsRequest, LLMStatus, RelationshipRequest, SessionCreated, SessionState,
    UploadError, UploadResponse,
)
from app.api.deps import accounts_of, current_user, detail_for, owned_session, session_of, sessions_of, settings_of, state_of
from app.api.security import rate_limit, require_token
from app.config import Settings
from app.data.loader import CHUNK_BYTES
from app.data.overview import build_overview
from app.errors import UserError
from app.logging_setup import log_event, session_id_var
from app.metrics import metrics
from app.models import QualityReport, Relationship, TableResult
from app.session import MAX_TRANSCRIPT_TURNS, Session

public = APIRouter(prefix="/api")
router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


def sample_files(settings: Settings) -> list[Path]:
    folder = Path(settings.sample_data_dir)
    return sorted(folder.glob("*.csv")) if folder.is_dir() else []


def sse(event: BaseModel) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


def save_upload_stream(file: UploadFile, destination: Path, limit_bytes: int, name: str, limit_mb: int) -> None:
    written = 0
    with destination.open("wb") as handle:
        while chunk := file.file.read(CHUNK_BYTES):
            written += len(chunk)
            if written > limit_bytes:
                handle.close()
                destination.unlink(missing_ok=True)
                raise UserError(f"'{name}' is larger than the {limit_mb} MB limit.", "file_too_large", 413)
            handle.write(chunk)


@public.get("/health")
def health() -> dict:
    return {"status": "ok"}


@public.get("/config")
def get_config(request: Request) -> AppConfig:
    s = settings_of(request)
    default = server_config(s)
    return AppConfig(
        llm_configured=default is not None, provider=s.llm_provider,
        model=default.resolved_model() if default else PROVIDER_DEFAULTS[s.llm_provider]["model"],
        default_models={name: info["model"] for name, info in PROVIDER_DEFAULTS.items()}, max_upload_mb=s.max_upload_mb,
        max_files_per_session=s.max_files_per_session, sql_timeout_seconds=s.sql_timeout_seconds,
        python_timeout_seconds=s.python_timeout_seconds, max_result_rows=s.max_result_rows,
        sample_datasets=[p.name for p in sample_files(s)], auth_required=bool(s.access_token) or s.auth_mode == "accounts",
        python_enabled=s.sandbox_mode != "off", auth_mode=s.auth_mode, registration_open=s.registration == "open",
        schedule_min_minutes=s.schedule_min_minutes, allow_private_connections=s.allow_private_connections,
    )


@router.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics(request: Request) -> str:
    return metrics.render({"datapilot_sessions_active": float(len(sessions_of(request).sessions))})


@router.post("/sessions", dependencies=[Depends(rate_limit("session_create", "session_create_per_hour", 3600))])
def create_session(request: Request) -> SessionCreated:
    user = current_user(request)
    session = sessions_of(request).create(user.id if user else None)
    session_id_var.set(session.id)
    log_event("session_created")
    return SessionCreated(session_id=session.id)


@router.get("/sessions/{session_id}")
def get_session(request: Request, session_id: str) -> SessionState:
    return state_of(request, session_of(request, session_id))


@router.get("/sessions/{session_id}/transcript")
def get_transcript(request: Request, session_id: str) -> list[dict]:
    return session_of(request, session_id).transcript


@router.delete("/sessions/{session_id}")
def delete_session(request: Request, session_id: str) -> dict:
    owned_session(request, session_id)
    sessions_of(request).delete(session_id)
    return {"deleted": True}


@router.post("/sessions/{session_id}/reset")
def reset_conversation(request: Request, session_id: str) -> SessionState:
    session = session_of(request, session_id)
    session.history, session.records, session.filters, session.transcript = [], [], {}, []
    sessions_of(request).save(session)
    return state_of(request, session)


@router.post("/sessions/{session_id}/datasets", dependencies=[Depends(rate_limit("upload", "upload_per_minute"))])
def upload_datasets(request: Request, session_id: str, files: list[UploadFile] = File(...)) -> UploadResponse:
    session = session_of(request, session_id)
    settings = settings_of(request)
    loaded, errors = [], []
    for file in files:
        name = file.filename or "unnamed"
        try:
            destination = session.store.incoming_path()
            save_upload_stream(file, destination, settings.max_upload_mb * 1024 * 1024, name, settings.max_upload_mb)
            profile = session.store.add_csv_path(name, destination)
            loaded.append(detail_for(session, profile.name))
            log_event("dataset_loaded", dataset=profile.name, rows=profile.rows, columns=profile.column_count)
        except UserError as exc:
            errors.append(UploadError(filename=name, message=exc.message))
            log_event("dataset_rejected", filename=name, reason=exc.code)
    sessions_of(request).save(session)
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
    sessions_of(request).save(session)
    return UploadResponse(datasets=loaded, errors=errors)


@router.delete("/sessions/{session_id}/datasets/{name}")
def delete_dataset(request: Request, session_id: str, name: str) -> SessionState:
    session = session_of(request, session_id)
    session.store.remove(name)
    if session.active_dataset == name:
        session.active_dataset = None
    sessions_of(request).save(session)
    return state_of(request, session)


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
    relationship = session.store.add_relationship((body.left_table, body.left_column), (body.right_table, body.right_column))
    sessions_of(request).save(session)
    return relationship


@router.put("/sessions/{session_id}/llm")
def set_llm(request: Request, session_id: str, body: LLMSettingsRequest) -> SessionState:
    session = session_of(request, session_id)
    config = LLMConfig(provider=body.provider, api_key=body.api_key, model=body.model.strip())
    session.llm = sessions_of(request).seal_llm(config)
    log_event("llm_configured", provider=body.provider, model=session.llm.model)
    return state_of(request, session)


@router.delete("/sessions/{session_id}/llm")
def clear_llm(request: Request, session_id: str) -> SessionState:
    session = session_of(request, session_id)
    session.llm = None
    return state_of(request, session)


@router.delete("/sessions/{session_id}/filters")
def clear_filters(request: Request, session_id: str) -> SessionState:
    session = session_of(request, session_id)
    session.filters = {}
    sessions_of(request).save(session)
    return state_of(request, session)


def check_quota(session: Session, settings: Settings) -> None:
    if session.llm is None and session.chat_turns >= settings.server_key_turn_limit:
        raise UserError(
            f"This session used its {settings.server_key_turn_limit} questions on the shared server key. Add your own API key in Settings to continue.",
            "quota_exceeded", 429,
        )


def event_stream(
    session: Session, body: ChatRequest, request: Request, llm_factory: Callable[[Settings, LLMConfig | None], LLMProvider]
) -> Iterator[str]:
    session_id_var.set(session.id)
    manager, settings = sessions_of(request), settings_of(request)
    if not session.lock.acquire(blocking=False):
        yield sse(ErrorEvent(message="Another question is still being answered in this session. Please wait for it to finish."))
        return
    entry = {"question": body.message, "events": []}
    outcome = "error"
    try:
        if body.dataset and body.dataset in session.store.profiles:
            session.active_dataset = body.dataset
        if not session.store.profiles:
            yield sse(ErrorEvent(message="Upload a CSV file first, then ask a question about it."))
            return
        log_event("chat_started", question_chars=len(body.message))
        override = manager.open_llm(session.llm) if session.llm else None
        for event in run_turn(session, body.message, llm_factory(settings, override)):
            append_event(entry["events"], event)
            if event.type == "done":
                outcome = "ok"
                session.chat_turns += 1
            yield sse(event)
    except (LLMError, UserError) as exc:
        message = exc.message
        append_event(entry["events"], ErrorEvent(message=message))
        yield sse(ErrorEvent(message=message))
    except Exception:
        log_event("chat_failed", exc_info=True)
        failure = ErrorEvent(message="Something went wrong while analysing your question. Please try again.")
        append_event(entry["events"], failure)
        yield sse(failure)
    finally:
        metrics.inc("datapilot_chat_turns_total", outcome=outcome)
        if entry["events"]:
            session.transcript = (session.transcript + [entry])[-MAX_TRANSCRIPT_TURNS:]
            manager.save(session)
        session.lock.release()


@router.post("/sessions/{session_id}/chat", dependencies=[Depends(rate_limit("chat", "chat_per_minute"))])
def chat(request: Request, session_id: str, body: ChatRequest) -> StreamingResponse:
    session = session_of(request, session_id)
    check_quota(session, settings_of(request))
    stream = event_stream(session, body, request, request.app.state.llm_factory)
    return StreamingResponse(
        stream, media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
