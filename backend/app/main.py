import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.llm import LLMConfig, LLMProvider, create_provider
from app.accounts import Accounts
from app.api import accounts_routes, connector_routes, schedule_routes, sharing_routes
from app.api.routes import public, router
from app.config import Settings, get_settings
from app.errors import UserError
from app.db import Database
from app.jobs import JobRunner
from app.schedules import Scheduler, Schedules
from app.sharing import Sharing
from app.limits import RateLimiter
from app.mailer import Mailer
from app.sso import Sso
from app.logging_setup import log_event, request_id_var, session_id_var, setup_logging
from app.metrics import metrics
from app.session import SessionManager


def error_response(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}}, headers=headers)


def create_app(
    settings: Settings | None = None, llm_factory: Callable[[Settings, LLMConfig | None], LLMProvider] = create_provider
) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    root = settings.sessions_root()
    db = Database(root / "app.db")
    mailer = Mailer(settings)
    accounts = Accounts(db, settings, mailer)
    manager = SessionManager(settings, accounts)
    schedules = Schedules(db, settings, mailer)
    scheduler = Scheduler(schedules, manager, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.scheduler_enabled:
            scheduler.start()
        yield
        scheduler.stop()
        app.state.jobs.shutdown()
        mailer.shutdown()

    app = FastAPI(title="DataPilot API", version="1.2.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.state.accounts = accounts
    app.state.mailer = mailer
    app.state.sso = Sso(db, settings, accounts)
    app.state.sessions = manager
    app.state.schedules = schedules
    app.state.scheduler = scheduler
    app.state.sharing = Sharing(db, settings)
    app.state.jobs = JobRunner()
    app.state.http_transport = None
    app.state.postgres_connect = None
    app.state.limiter = RateLimiter()
    app.state.llm_factory = llm_factory
    restored = app.state.sessions.restore_all()
    log_event("sessions_restored", count=restored)

    app.add_middleware(
        CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID", "Retry-After"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
        request_id_var.set(request_id)
        session_id_var.set("-")
        started = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - started
        route = request.scope.get("route")
        path_label = route.path if route else "unmatched"
        response.headers["X-Request-ID"] = request_id
        metrics.inc("datapilot_http_requests_total", method=request.method, path=path_label, status=response.status_code)
        metrics.inc("datapilot_http_request_seconds_sum", duration, path=path_label)
        log_event(
            "request", method=request.method, path=request.url.path, status=response.status_code,
            duration_ms=round(duration * 1000, 1),
        )
        return response

    @app.exception_handler(UserError)
    async def handle_user_error(request: Request, exc: UserError):
        return error_response(exc.status, exc.code, exc.message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        fields = ", ".join(".".join(str(p) for p in e["loc"] if p != "body") for e in exc.errors())
        return error_response(422, "invalid_request", f"The request was invalid. Check these fields: {fields}.")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        log_event("unhandled_error", exc_info=(type(exc), exc, exc.__traceback__), path=request.url.path)
        return error_response(500, "internal_error", "Something went wrong on the server. Please try again.")

    app.include_router(public)
    app.include_router(accounts_routes.public)
    app.include_router(accounts_routes.router)
    app.include_router(sharing_routes.public)
    app.include_router(sharing_routes.router)
    app.include_router(schedule_routes.router)
    app.include_router(connector_routes.router)
    app.include_router(router)
    return app


app = create_app()
