import hmac

from fastapi import Request

from app.errors import UserError


def client_ip(request: Request) -> str:
    if request.app.state.settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def require_token(request: Request) -> None:
    settings = request.app.state.settings
    if settings.auth_mode == "accounts":
        token = bearer_token(request)
        user = request.app.state.accounts.user_for_token(token) if token else None
        if user is None:
            raise UserError("Please sign in to continue.", "unauthorized", 401)
        request.state.user = user
        request.state.token = token
        return
    if not settings.access_token:
        return
    supplied = request.headers.get("authorization", "")
    if not hmac.compare_digest(supplied.encode(), f"Bearer {settings.access_token}".encode()):
        raise UserError("An access token is required. Enter it to continue.", "unauthorized", 401)


def rate_limit(scope: str, setting_name: str, window_seconds: float = 60):
    def dependency(request: Request) -> None:
        limit = getattr(request.app.state.settings, setting_name)
        request.app.state.limiter.check(scope, client_ip(request), limit, window_seconds)

    return dependency
