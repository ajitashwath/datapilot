from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.accounts import Member, Team, User
from app.api.deps import accounts_of, current_user, owned_session, settings_of, state_of
from app.api.schemas import SessionState
from app.api.security import bearer_token, client_ip, rate_limit, require_token
from app.errors import UserError

public = APIRouter(prefix="/api/auth")
router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


class RegisterRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    name: str = Field(max_length=80)


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class AuthResponse(BaseModel):
    token: str
    user: User


class TeamCreate(BaseModel):
    name: str = Field(max_length=80)


class MemberAdd(BaseModel):
    email: str = Field(max_length=254)
    role: str = "member"


class WorkspacePatch(BaseModel):
    name: str | None = Field(None, max_length=80)
    team_id: str | None = None


class WorkspaceInfo(BaseModel):
    session_id: str
    name: str
    role: str
    team_id: str | None
    team_name: str | None
    updated_at: float


def accounts_enabled(request: Request) -> None:
    if settings_of(request).auth_mode != "accounts":
        raise UserError("Accounts are not enabled on this server.", "accounts_disabled", 404)


def signed_in(request: Request) -> User:
    user = current_user(request)
    if user is None:
        raise UserError("Please sign in to continue.", "unauthorized", 401)
    return user


def throttle_login(request: Request, email: str) -> None:
    limit = settings_of(request).login_per_minute
    limiter = request.app.state.limiter
    limiter.check("login_ip", client_ip(request), limit, 60)
    limiter.check("login_email", email.strip().lower(), limit, 60)


@public.post("/register", dependencies=[Depends(accounts_enabled)])
def register(request: Request, body: RegisterRequest) -> AuthResponse:
    throttle_login(request, body.email)
    accounts = accounts_of(request)
    accounts.register(body.email, body.password, body.name)
    token, user = accounts.login(body.email, body.password)
    return AuthResponse(token=token, user=user)


@public.post("/login", dependencies=[Depends(accounts_enabled)])
def login(request: Request, body: LoginRequest) -> AuthResponse:
    throttle_login(request, body.email)
    token, user = accounts_of(request).login(body.email, body.password)
    return AuthResponse(token=token, user=user)


@router.post("/auth/logout", dependencies=[Depends(accounts_enabled)])
def logout(request: Request) -> dict:
    accounts_of(request).logout(bearer_token(request))
    return {"signed_out": True}


@router.get("/auth/me", dependencies=[Depends(accounts_enabled)])
def me(request: Request) -> User:
    return signed_in(request)


@router.get("/teams", dependencies=[Depends(accounts_enabled)])
def list_teams(request: Request) -> list[Team]:
    return accounts_of(request).teams_for(signed_in(request))


@router.post("/teams", dependencies=[Depends(accounts_enabled)])
def create_team(request: Request, body: TeamCreate) -> Team:
    return accounts_of(request).create_team(signed_in(request), body.name)


@router.get("/teams/{team_id}/members", dependencies=[Depends(accounts_enabled)])
def list_members(request: Request, team_id: str) -> list[Member]:
    return accounts_of(request).members(signed_in(request), team_id)


@router.post("/teams/{team_id}/members", dependencies=[Depends(accounts_enabled)])
def add_member(request: Request, team_id: str, body: MemberAdd) -> Member:
    return accounts_of(request).add_member(signed_in(request), team_id, body.email, body.role)


@router.delete("/teams/{team_id}/members/{user_id}", dependencies=[Depends(accounts_enabled)])
def remove_member(request: Request, team_id: str, user_id: str) -> dict:
    accounts_of(request).remove_member(signed_in(request), team_id, user_id)
    return {"removed": True}


@router.get("/sessions", dependencies=[Depends(accounts_enabled)])
def list_workspaces(request: Request) -> list[WorkspaceInfo]:
    user = signed_in(request)
    accounts = accounts_of(request)
    infos = []
    for row in accounts.workspaces_for(user):
        role = accounts.access(row["session_id"], user)
        if role:
            infos.append(WorkspaceInfo(
                session_id=row["session_id"], name=row["name"], role=role, team_id=row["team_id"],
                team_name=row["team_name"], updated_at=row["updated_at"],
            ))
    return infos


@router.patch("/sessions/{session_id}")
def update_workspace(request: Request, session_id: str, body: WorkspacePatch) -> SessionState:
    session = owned_session(request, session_id)
    accounts = accounts_of(request)
    if body.name is not None:
        accounts.rename_workspace(session_id, body.name)
    if "team_id" in body.model_fields_set:
        if settings_of(request).auth_mode != "accounts":
            raise UserError("Accounts are not enabled on this server.", "accounts_disabled", 404)
        accounts.set_team(session_id, current_user(request), body.team_id)
    return state_of(request, session)
