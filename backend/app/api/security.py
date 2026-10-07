import hmac

from fastapi import Request

from app.errors import UserError


def client_ip(request: Request) -> str:
    if request.app.state.settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def require_token(request: Request) -> None:
    token = request.app.state.settings.access_token
    if not token:
        return
    supplied = request.headers.get("authorization", "")
    if not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
        raise UserError("An access token is required. Enter it to continue.", "unauthorized", 401)


def rate_limit(scope: str, setting_name: str, window_seconds: float = 60):
    def dependency(request: Request) -> None:
        limit = getattr(request.app.state.settings, setting_name)
        request.app.state.limiter.check(scope, client_ip(request), limit, window_seconds)

    return dependency
