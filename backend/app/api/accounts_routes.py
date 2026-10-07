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
    token: str | None
    user: User
    verification_required: bool = False
    two_factor_required: bool = False
    challenge: str | None = None


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
    user = accounts.register(body.email, body.password, body.name)
    if accounts.needs_verification():
        return AuthResponse(token=None, user=user, verification_required=True)
    token, user = accounts.login(body.email, body.password)
    return AuthResponse(token=token, user=user)


@public.post("/login", dependencies=[Depends(accounts_enabled)])
def login(request: Request, body: LoginRequest) -> AuthResponse:
    throttle_login(request, body.email)
    token, user, challenge = accounts_of(request).begin_login(body.email, body.password)
    return AuthResponse(token=token, user=user, two_factor_required=challenge is not None, challenge=challenge)


class TwoFactorLogin(BaseModel):
    challenge: str = Field(min_length=10, max_length=200)
    code: str = Field(min_length=6, max_length=20)


class PasswordOnly(BaseModel):
    password: str = Field(max_length=200)


class CodeOnly(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class TwoFactorDisable(BaseModel):
    password: str = Field(max_length=200)
    code: str = Field(min_length=6, max_length=20)


class SsoCallback(BaseModel):
    code: str = Field(min_length=1, max_length=2000)
    state: str = Field(min_length=10, max_length=200)


@public.get("/sso/start", dependencies=[Depends(accounts_enabled)])
def sso_start(request: Request) -> dict:
    request.app.state.limiter.check("sso_start", client_ip(request), settings_of(request).login_per_minute, 60)
    return {"url": request.app.state.sso.start(request.app.state.http_transport)}


@public.post("/sso/callback", dependencies=[Depends(accounts_enabled)])
def sso_callback(request: Request, body: SsoCallback) -> AuthResponse:
    request.app.state.limiter.check("sso_callback", client_ip(request), settings_of(request).login_per_minute, 60)
    token, user = request.app.state.sso.finish(body.code, body.state, request.app.state.http_transport)
    return AuthResponse(token=token, user=user)


@public.post("/login/2fa", dependencies=[Depends(accounts_enabled)])
def login_with_code(request: Request, body: TwoFactorLogin) -> AuthResponse:
    accounts = accounts_of(request)
    limiter = request.app.state.limiter
    limiter.check("twofa_ip", client_ip(request), settings_of(request).login_per_minute, 60)
    owner = accounts.challenge_user_id(body.challenge)
    limiter.check("twofa_user", owner or "unknown", 10, 900)
    token, user = accounts.finish_login(body.challenge, body.code)
    return AuthResponse(token=token, user=user)


class TokenBody(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class EmailBody(BaseModel):
    email: str = Field(max_length=254)


class ResetBody(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


def email_ready(request: Request) -> None:
    if not accounts_of(request).mailer.enabled:
        raise UserError("Email is not set up on this server, so this is unavailable. Ask an administrator.", "email_disabled", 501)


def throttle_email(request: Request, scope: str, email: str) -> None:
    limit = settings_of(request).forgot_per_hour
    limiter = request.app.state.limiter
    limiter.check(scope + "_ip", client_ip(request), limit * 3, 3600)
    limiter.check(scope + "_email", email.strip().lower(), limit, 3600)


@public.post("/forgot", dependencies=[Depends(accounts_enabled), Depends(email_ready)])
def forgot_password(request: Request, body: EmailBody) -> dict:
    throttle_email(request, "forgot", body.email)
    accounts_of(request).forgot_password(body.email)
    return {"sent": True}


@public.post("/reset", dependencies=[Depends(accounts_enabled)])
def reset_password(request: Request, body: ResetBody) -> dict:
    throttle_login(request, "reset-attempt")
    accounts_of(request).reset_password(body.token, body.password)
    return {"reset": True}


@public.post("/verify", dependencies=[Depends(accounts_enabled)])
def verify_email(request: Request, body: TokenBody) -> dict:
    throttle_login(request, "verify-attempt")
    accounts_of(request).verify_email(body.token)
    return {"verified": True}


@public.post("/resend-verification", dependencies=[Depends(accounts_enabled), Depends(email_ready)])
def resend_verification(request: Request, body: EmailBody) -> dict:
    throttle_email(request, "resend", body.email)
    accounts_of(request).resend_verification(body.email)
    return {"sent": True}


@router.post("/auth/password", dependencies=[Depends(accounts_enabled)])
def change_password(request: Request, body: PasswordChange) -> dict:
    accounts_of(request).change_password(signed_in(request), body.current_password, body.new_password, bearer_token(request))
    return {"changed": True}


@router.get("/auth/2fa", dependencies=[Depends(accounts_enabled)])
def two_factor_status(request: Request) -> dict:
    return accounts_of(request).two_factor_status(signed_in(request))


@router.post("/auth/2fa/setup", dependencies=[Depends(accounts_enabled)])
def two_factor_setup(request: Request, body: PasswordOnly) -> dict:
    user = signed_in(request)
    request.app.state.limiter.check("twofa_setup", user.id, 10, 900)
    return accounts_of(request).start_two_factor(user, body.password)


@router.post("/auth/2fa/enable", dependencies=[Depends(accounts_enabled)])
def two_factor_enable(request: Request, body: CodeOnly) -> dict:
    user = signed_in(request)
    request.app.state.limiter.check("twofa_enable", user.id, 10, 900)
    return {"recovery_codes": accounts_of(request).enable_two_factor(user, body.code, bearer_token(request))}


@router.post("/auth/2fa/disable", dependencies=[Depends(accounts_enabled)])
def two_factor_disable(request: Request, body: TwoFactorDisable) -> dict:
    user = signed_in(request)
    request.app.state.limiter.check("twofa_disable", user.id, 10, 900)
    accounts_of(request).disable_two_factor(user, body.password, body.code)
    return {"disabled": True}


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
