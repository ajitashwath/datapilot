import time
import uuid
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.llm import LLMProvider, create_provider
from app.api.routes import router
from app.config import Settings, get_settings
from app.errors import UserError
from app.logging_setup import log_event, request_id_var, session_id_var, setup_logging
from app.session import SessionManager


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(
    settings: Settings | None = None, llm_factory: Callable[[Settings], LLMProvider] = create_provider
) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(title="DataPilot API", version="1.0.0")
    app.state.settings = settings
    app.state.sessions = SessionManager(settings)
    app.state.llm_factory = llm_factory

    app.add_middleware(
        CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
        request_id_var.set(request_id)
        session_id_var.set("-")
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        log_event(
            "request", method=request.method, path=request.url.path, status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return response

    @app.exception_handler(UserError)
    async def handle_user_error(request: Request, exc: UserError):
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        fields = ", ".join(".".join(str(p) for p in e["loc"] if p != "body") for e in exc.errors())
        return error_response(422, "invalid_request", f"The request was invalid. Check these fields: {fields}.")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        log_event("unhandled_error", exc_info=(type(exc), exc, exc.__traceback__), path=request.url.path)
        return error_response(500, "internal_error", "Something went wrong on the server. Please try again.")

    app.include_router(router)
    return app


app = create_app()
