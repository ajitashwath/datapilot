from fastapi import Request

from app.accounts import Accounts, User
from app.api.schemas import DatasetDetail, LLMStatus, SessionState
from app.config import Settings
from app.errors import UserError
from app.logging_setup import session_id_var
from app.session import Session, SessionManager

READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def sessions_of(request: Request) -> SessionManager:
    return request.app.state.sessions


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


def accounts_of(request: Request) -> Accounts:
    return request.app.state.accounts


def current_user(request: Request) -> User | None:
    return getattr(request.state, "user", None)


def role_for(request: Request, session_id: str) -> str:
    if settings_of(request).auth_mode != "accounts":
        return "owner"
    user = current_user(request)
    role = accounts_of(request).access(session_id, user) if user else None
    if role is None:
        raise UserError("This session has expired or does not exist. Please start a new one.", "session_not_found", 404)
    return role


def session_of(request: Request, session_id: str) -> Session:
    session_id_var.set(session_id)
    role = role_for(request, session_id)
    if role == "reader" and request.method not in READ_METHODS:
        raise UserError("You have read-only access to this workspace.", "read_only", 403)
    return sessions_of(request).get(session_id)


def owned_session(request: Request, session_id: str) -> Session:
    session = session_of(request, session_id)
    if role_for(request, session_id) != "owner":
        raise UserError("Only the workspace owner can do this.", "forbidden", 403)
    return session


def detail_for(session: Session, name: str) -> DatasetDetail:
    quality = session.store.get_quality(name)
    return DatasetDetail(profile=session.store.get_profile(name), quality_score=quality.score, issue_count=len(quality.issues))


def state_of(request: Request, session: Session) -> SessionState:
    workspace = accounts_of(request).workspace(session.id) or {}
    return SessionState(
        session_id=session.id,
        name=workspace.get("name", "Untitled analysis"),
        role=role_for(request, session.id),
        team_id=workspace.get("team_id"),
        datasets=[detail_for(session, name) for name in session.store.profiles],
        relationships=session.store.relationships,
        filters=session.filters,
        active_dataset=session.active_dataset,
        llm=LLMStatus(provider=session.llm.provider, model=session.llm.model) if session.llm else None,
    )
