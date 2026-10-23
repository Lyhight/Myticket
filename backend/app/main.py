from contextlib import asynccontextmanager
import logging
import re
import secrets
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.routing import Match

from app.api.v1.db_check import router as db_check_router
from app.api.v1.health import router as health_router
from app.core.config import settings
from app.api.v1.users import router as users_router
from app.api.v1.auth import router as auth_router
from app.api.v1.tickets import router as tickets_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.operations import router as operations_router
from app.api.v1.events import router as events_router
from app.api.v1.feedback import router as feedback_router
from app.operations.rate_limit import close_rate_limit_backend
from app.core.logging import (
    configure_logging,
    reset_correlation_id,
    set_correlation_id,
)
from app.operations.observability import HTTP_DURATION, HTTP_REQUESTS


configure_logging()
logger = logging.getLogger(__name__)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _route_template(request: Request, original_path: str) -> str:
    # Nested routers may rewrite scope["path"] while dispatching. Match a
    # copy restored to the original URL path so the metric label keeps the
    # complete registered template without using concrete path parameters.
    match_scope = {
        "type": "http",
        "path": original_path,
        "root_path": "",
        "method": request.method,
    }
    for registered_route in app.routes:
        match, child_scope = registered_route.matches(match_scope)
        if match == Match.FULL:
            direct_path = getattr(registered_route, "path", None)
            if direct_path:
                return str(direct_path)
            child_route = child_scope.get("route")
            child_path = getattr(child_route, "path", None)
            include_context = getattr(
                registered_route,
                "include_context",
                None,
            )
            prefix = getattr(include_context, "prefix", "")
            if child_path:
                return f"{prefix}{child_path}"
            original_router = getattr(
                registered_route,
                "original_router",
                None,
            )
            if original_router is not None and original_path.startswith(prefix):
                nested_scope = dict(match_scope)
                nested_scope["path"] = original_path[len(prefix):] or "/"
                for nested_route in original_router.routes:
                    nested_match, _ = nested_route.matches(nested_scope)
                    if nested_match == Match.FULL:
                        nested_path = getattr(nested_route, "path", None)
                        if nested_path:
                            return f"{prefix}{nested_path}"
    return "unmatched"


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_rate_limit_backend()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI Customer Service Agent Platform Backend",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    scope_path = request.scope["path"]
    scope_root = request.scope.get("root_path", "")
    original_path = (
        f"{scope_root}{scope_path}"
        if scope_root and not scope_path.startswith(scope_root)
        else scope_path
    )
    supplied_request_id = request.headers.get("X-Request-ID", "")
    request_id = (
        supplied_request_id
        if _REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
        else uuid4().hex
    )
    request.state.request_id = request_id
    correlation_token = set_correlation_id(request_id)
    started = perf_counter()
    status_code = 500
    route = "unmatched"
    try:
        response = await call_next(request)
        status_code = response.status_code
        route = _route_template(request, original_path)
        duration = perf_counter() - started
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = str(round(duration * 1000, 3))
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response
    except Exception:
        logger.exception("http_request_failed")
        raise
    finally:
        duration = perf_counter() - started
        HTTP_REQUESTS.labels(
            method=request.method,
            route=route,
            status=str(status_code),
        ).inc()
        HTTP_DURATION.labels(
            method=request.method,
            route=route,
        ).observe(duration)
        logger.info(
            "http_request_completed",
            extra={
                "event": "http_request_completed",
                "method": request.method,
                "route": route,
                "status_code": status_code,
                "duration_ms": round(duration * 1000, 3),
            },
        )
        reset_correlation_id(correlation_token)


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics(request: Request) -> Response:
    expected_token = settings.metrics_bearer_token
    if expected_token:
        authorization = request.headers.get("Authorization", "")
        scheme, _, supplied_token = authorization.partition(" ")
        if (
            scheme.lower() != "bearer"
            or not secrets.compare_digest(supplied_token, expected_token)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Metrics authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root():
    return {
        "message": f"{settings.app_name} is running",
        "version": settings.app_version,
        "debug": settings.debug,
    }


app.include_router(
    health_router,
    prefix="/api/v1",
)

app.include_router(
    db_check_router,
    prefix="/api/v1",
)
app.include_router(
    users_router,
    prefix="/api/v1",
)
app.include_router(
    auth_router,
    prefix="/api/v1",
)
app.include_router(
    tickets_router,
    prefix="/api/v1",
)
app.include_router(
    knowledge_router,
    prefix="/api/v1",
)
app.include_router(
    operations_router,
    prefix="/api/v1",
)
app.include_router(
    events_router,
    prefix="/api/v1",
)
app.include_router(
    feedback_router,
    prefix="/api/v1",
)
