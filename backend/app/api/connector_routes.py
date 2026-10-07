from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import role_for, session_of, sessions_of, settings_of
from app.api.routes import save_upload_stream
from app.api.security import rate_limit, require_token
from app.connectors import (
    PostgresConnection, import_postgres, import_sqlite, import_url, list_postgres_tables, refresh_dataset,
)
from app.errors import UserError
from app.logging_setup import log_event
from app.session import Session

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


class UrlImport(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    name: str | None = Field(None, max_length=80)


class PostgresImport(BaseModel):
    connection: PostgresConnection
    tables: list[str] = Field(default_factory=list, max_length=20)


class PostgresTables(BaseModel):
    connection: PostgresConnection


def finish_job(request: Request, session: Session, kind: str, work):
    manager = sessions_of(request)

    def run() -> list[str]:
        created = work()
        manager.save(session)
        return created

    job = request.app.state.jobs.submit(session.id, kind, run)
    log_event("job_submitted", kind=kind)
    return {"job_id": job.id}


@router.post("/sessions/{session_id}/connectors/url", dependencies=[Depends(rate_limit("upload", "upload_per_minute"))])
def connect_url(request: Request, session_id: str, body: UrlImport) -> dict:
    session = session_of(request, session_id)
    settings, transport = settings_of(request), request.app.state.http_transport
    return finish_job(request, session, "url", lambda: import_url(session, settings, body.url, body.name, transport))


@router.post("/sessions/{session_id}/connectors/sqlite", dependencies=[Depends(rate_limit("upload", "upload_per_minute"))])
def connect_sqlite(request: Request, session_id: str, file: UploadFile = File(...)) -> dict:
    session = session_of(request, session_id)
    settings = settings_of(request)
    name = file.filename or "database.sqlite"
    destination = session.store.incoming_path()
    save_upload_stream(file, destination, settings.max_upload_mb * 1024 * 1024, name, settings.max_upload_mb)

    def work() -> list[str]:
        try:
            return import_sqlite(session, settings, destination, name)
        finally:
            destination.unlink(missing_ok=True)

    return finish_job(request, session, "sqlite", work)


@router.post("/sessions/{session_id}/connectors/postgres/tables", dependencies=[Depends(rate_limit("upload", "upload_per_minute"))])
def postgres_tables(request: Request, session_id: str, body: PostgresTables) -> dict:
    session_of(request, session_id)
    connect = request.app.state.postgres_connect
    return {"tables": list_postgres_tables(body.connection, settings_of(request), connect)}


@router.post("/sessions/{session_id}/connectors/postgres", dependencies=[Depends(rate_limit("upload", "upload_per_minute"))])
def connect_postgres(request: Request, session_id: str, body: PostgresImport) -> dict:
    session = session_of(request, session_id)
    settings, connect = settings_of(request), request.app.state.postgres_connect
    return finish_job(request, session, "postgres", lambda: import_postgres(session, settings, body.connection, body.tables, connect))


@router.post("/sessions/{session_id}/datasets/{name}/refresh", dependencies=[Depends(rate_limit("upload", "upload_per_minute"))])
def refresh(request: Request, session_id: str, name: str) -> dict:
    session = session_of(request, session_id)
    settings, transport = settings_of(request), request.app.state.http_transport
    session.store.get_profile(name)
    return finish_job(request, session, "refresh", lambda: refresh_dataset(session, settings, name, transport))


@router.get("/jobs/{job_id}")
def job_status(request: Request, job_id: str) -> dict:
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise UserError("Job not found.", "job_not_found", 404)
    role_for(request, job.session_id)
    return {"id": job.id, "kind": job.kind, "status": job.status, "message": job.message, "datasets": job.datasets}
