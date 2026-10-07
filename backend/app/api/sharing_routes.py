from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.deps import current_user, owned_session
from app.api.security import rate_limit, require_token

public = APIRouter(prefix="/api")
router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


class ShareCreate(BaseModel):
    title: str = Field("", max_length=120)


@router.post("/sessions/{session_id}/shares")
def create_share(request: Request, session_id: str, body: ShareCreate) -> dict:
    session = owned_session(request, session_id)
    user = current_user(request)
    return request.app.state.sharing.create(session, body.title, user.id if user else None)


@router.get("/sessions/{session_id}/shares")
def list_shares(request: Request, session_id: str) -> list[dict]:
    owned_session(request, session_id)
    return request.app.state.sharing.for_session(session_id)


@router.delete("/sessions/{session_id}/shares/{token}")
def revoke_share(request: Request, session_id: str, token: str) -> dict:
    owned_session(request, session_id)
    request.app.state.sharing.revoke(session_id, token)
    return {"revoked": True}


@public.get("/shared/{token}", dependencies=[Depends(rate_limit("shared", "shared_per_minute"))])
def read_shared(request: Request, token: str) -> JSONResponse:
    snapshot = request.app.state.sharing.snapshot(token)
    return JSONResponse(snapshot, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"})
