# app/main.py
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
import os
import secrets
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.endpoints import (
    conversation,
    auth,
    personal_docs,
    user,
    evaluation,
    llm_stats,
    agent,
    diet,
    community,
    meta,
    mcp,
    events,
)
from app.config import settings
from app.database.session import init_db, close_db
from app.database.document_repository import DocumentRepository
from app.services.auth_service import auth_service
from app.security.middleware.rate_limiter import rate_limiter
from app.security.sanitizer import setup_secure_logging
from app.security.audit import audit_logger
import logging
from app.utils.logger import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

# Setup secure logging with sensitive data filtering
setup_secure_logging()


def _clamp_0_1(value: float) -> float:
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


def _read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


def _init_sentry() -> None:
    """
    Optional Sentry error tracking.

    Enabled only when SENTRY_DSN is configured. This keeps local dev / CI
    deterministic and avoids accidentally sending data without explicit opt-in.
    """
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
    except Exception as exc:  # pragma: no cover - optional dependency / env gated
        logger.warning("Sentry is enabled but sentry-sdk failed to import: %s", exc)
        return

    traces_sample_rate = _clamp_0_1(
        _read_float_env("SENTRY_TRACES_SAMPLE_RATE", 0.0)
    )
    profiles_sample_rate = _clamp_0_1(
        _read_float_env("SENTRY_PROFILES_SAMPLE_RATE", 0.0)
    )
    environment = (
        os.getenv("SENTRY_ENVIRONMENT")
        or os.getenv("ENVIRONMENT")
        or ("production" if os.getenv("RENDER") else "development")
    )

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=os.getenv("SENTRY_RELEASE"),
        integrations=[FastApiIntegration()],
        send_default_pii=False,
        # Avoid sending request bodies to Sentry by default.
        max_request_body_size="never",
        traces_sample_rate=traces_sample_rate,
        profiles_sample_rate=profiles_sample_rate,
    )
    logger.info("Sentry initialized. env=%s traces=%.3f", environment, traces_sample_rate)


_init_sentry()

_TRUTHY_VALUES = {"1", "true", "yes", "y", "on"}


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in _TRUTHY_VALUES


def _load_cors_origins() -> list[str]:
    """
    Load CORS allowed origins from environment.

    Environment:
    - CORS_ALLOW_ORIGINS: comma-separated origins
      Example: "https://frontend-one-gray-39.vercel.app,http://localhost:5173"
    """
    raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if raw:
        origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
        if origins:
            return origins

    # Safe defaults for local development and current production frontend
    return [
        "http://localhost:5173",
        "http://localhost:8000",
        "http://localhost:8080",
        "https://frontend-one-gray-39.vercel.app",
    ]


def _load_cors_origin_regex() -> str | None:
    """
    Load optional CORS origin regex from environment.

    If not configured, allow Vercel preview/production subdomains by default
    so frontend redeploys do not break cross-origin requests.
    """
    raw = os.getenv("CORS_ALLOW_ORIGIN_REGEX", "").strip()
    if raw:
        return raw
    return r"^https://.*\.vercel\.app$"


async def _run_non_blocking_startup_tasks() -> None:
    """Run non-critical startup tasks in background to avoid blocking port bind."""
    from app.agent import setup_mcp_servers

    mcp_timeout = float(os.getenv("MCP_STARTUP_TIMEOUT_SECONDS", "60"))
    metadata_timeout = float(os.getenv("METADATA_CACHE_TIMEOUT_SECONDS", "20"))

    logger.info("Registering MCP servers in background...")
    try:
        task = asyncio.create_task(setup_mcp_servers())

        # Ensure task exceptions are always retrieved to avoid "Task exception was never retrieved".
        def _consume_task_result(t: asyncio.Task) -> None:
            try:
                _ = t.exception()
            except asyncio.CancelledError:
                return

        task.add_done_callback(_consume_task_result)

        # This function already runs in a background task, so timeout should not cancel the
        # underlying MCP setup. Shield keeps the MCP setup running even if we stop awaiting it.
        await asyncio.wait_for(asyncio.shield(task), timeout=mcp_timeout)
        logger.info("MCP servers registered.")
    except asyncio.TimeoutError:
        logger.warning("MCP registration timed out after %.1fs; continuing.", mcp_timeout)
    except Exception as e:
        logger.warning(f"Failed to register MCP servers: {e}")

    logger.info("Initializing metadata cache in background...")
    try:
        await asyncio.wait_for(
            DocumentRepository.init_all_metadata_cache(),
            timeout=metadata_timeout,
        )
        logger.info("Metadata cache initialized.")
    except asyncio.TimeoutError:
        logger.warning(
            "Metadata cache initialization timed out after %.1fs; continuing.",
            metadata_timeout,
        )
    except Exception as e:
        logger.warning(f"Failed to initialize metadata cache: {e}")


async def _initialize_database_or_raise(timeout_seconds: float) -> None:
    logger.info("Initializing database...")
    await asyncio.wait_for(init_db(), timeout=timeout_seconds)
    logger.info("Database initialized.")


async def _retry_database_initialization(
    app: FastAPI,
    timeout_seconds: float,
    retry_interval_seconds: float,
) -> None:
    while not getattr(app.state, "db_ready", False):
        try:
            await _initialize_database_or_raise(timeout_seconds=timeout_seconds)
            app.state.db_ready = True
            logger.info("Database recovery succeeded; service is fully ready.")
            return
        except Exception as exc:
            logger.warning(
                "Database initialization retry failed: %s. Retrying in %.1fs.",
                exc,
                retry_interval_seconds,
            )
            await asyncio.sleep(retry_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    background_startup_task: asyncio.Task | None = None
    db_recovery_task: Optional[asyncio.Task] = None

    # Startup

    # Security check: Validate JWT secret key
    if not settings.JWT_SECRET_KEY:
        generated_secret = secrets.token_urlsafe(48)
        settings.JWT_SECRET_KEY = generated_secret
        auth_service.secret_key = generated_secret
        logger.warning(
            "JWT_SECRET_KEY is not set. Generated an ephemeral key for this process. "
            "Set JWT_SECRET_KEY in Render env for stable login sessions."
        )

    app.state.db_ready = False
    db_init_timeout = float(os.getenv("DB_INIT_TIMEOUT_SECONDS", "25"))
    db_init_fail_open = _is_truthy(os.getenv("DB_INIT_FAIL_OPEN", "true"))
    db_init_retry_seconds = float(os.getenv("DB_INIT_RETRY_SECONDS", "8"))

    try:
        await _initialize_database_or_raise(timeout_seconds=db_init_timeout)
        app.state.db_ready = True
    except Exception as exc:
        logger.error("Database initialization failed: %s", exc)
        if not db_init_fail_open:
            raise
        logger.warning(
            "DB_INIT_FAIL_OPEN=true, continue startup in degraded mode and retry in background."
        )
        db_recovery_task = asyncio.create_task(
            _retry_database_initialization(
                app=app,
                timeout_seconds=db_init_timeout,
                retry_interval_seconds=db_init_retry_seconds,
            )
        )

    # Initialize Agent module (registers default agent, tools, skills)
    logger.info("Initializing Agent module...")
    from app.agent import setup_agent_module, setup_mcp_servers

    setup_agent_module()
    logger.info("Agent module initialized.")

    # Non-critical tasks run in background so server can bind port quickly on cloud.
    # Tests may disable these tasks to keep the suite deterministic.
    if _is_truthy(os.getenv("DISABLE_BACKGROUND_STARTUP_TASKS", "false")):
        logger.info(
            "Background startup tasks are disabled (DISABLE_BACKGROUND_STARTUP_TASKS=true)."
        )
    else:
        background_startup_task = asyncio.create_task(_run_non_blocking_startup_tasks())

    # Keep startup lightweight for cloud deploys.
    # Heavy RAG initialization is deferred until first retrieval request by default.
    if os.getenv("RAG_INIT_ON_STARTUP", "false").lower() == "true":
        from app.services.rag_service import get_rag_service

        rag_service = get_rag_service()
        if rag_service.cache_manager and rag_service.cache_manager.redis_client:
            # Initialize rate limiter with Redis client
            rate_limiter.set_redis(rag_service.cache_manager.redis_client)
            logger.info("Rate limiter initialized with Redis.")
            # Initialize auth service with Redis client for login tracking
            auth_service.set_redis(rag_service.cache_manager.redis_client)
            logger.info("Auth service initialized with Redis for login tracking.")
    else:
        logger.info("Skipping eager RAG init at startup (RAG_INIT_ON_STARTUP=false).")

    yield
    # Shutdown
    if background_startup_task and not background_startup_task.done():
        background_startup_task.cancel()
    if db_recovery_task and not db_recovery_task.done():
        db_recovery_task.cancel()

    logger.info("Closing database connections...")
    await close_db()
    logger.info("Database connections closed.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="The backend API for the CookHero intelligent dietary assistant.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=_load_cors_origins(),
    allow_origin_regex=_load_cors_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


EXEMPT_PATHS = {
    f"{settings.API_V1_STR}/auth/login",
    f"{settings.API_V1_STR}/auth/register",
    f"{settings.API_V1_STR}/mcp/diet-adjust",
}


@app.middleware("http")
async def auth_gateway(request: Request, call_next):
    """Simple gateway: require JWT for all routes except login/register/docs/root."""
    # Allow CORS preflight through without requiring auth.
    # This is necessary for cross-origin fallback calls (e.g. direct Render URL).
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if (
        path in EXEMPT_PATHS
        or path == "/"
        or path.startswith("/docs")
        or path.startswith("/redoc")
        or path.startswith("/openapi")
        or path.startswith("/static")
    ):
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return JSONResponse(status_code=401, content={"detail": "需要登录"})

    token = auth_header.split(" ", 1)[1].strip()
    identity = auth_service.decode_token(token)
    if not identity or not identity.get("username"):
        return JSONResponse(
            status_code=401, content={"detail": "登录已失效，请重新登录"}
        )

    # Attach user info to request state for downstream use (e.g., filtering by user)
    request.state.username = identity.get("username")
    request.state.user_id = identity.get("user_id")

    return await call_next(request)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware using Redis."""
    # Always allow CORS preflight through. Browsers send OPTIONS without auth
    # headers, and blocking it breaks cross-origin fallback requests.
    if request.method == "OPTIONS":
        return await call_next(request)

    # Check rate limit
    rate_limit_response = await rate_limiter.check_rate_limit(request)
    if rate_limit_response:
        # Log rate limit exceeded
        audit_logger.rate_limit_exceeded(
            request=request,
            user_id=getattr(request.state, "user_id", None),
            endpoint=str(request.url.path),
        )
        return rate_limit_response

    return await call_next(request)


@app.middleware("http")
async def readiness_gate(request: Request, call_next):
    """Gate non-exempt routes when database is not ready."""
    # Allow CORS preflight even during startup gates.
    if request.method == "OPTIONS":
        return await call_next(request)

    if getattr(request.app.state, "db_ready", True):
        return await call_next(request)

    path = request.url.path
    if (
        path in EXEMPT_PATHS
        or path == "/"
        or path.startswith("/docs")
        or path.startswith("/redoc")
        or path.startswith("/openapi")
        or path.startswith("/static")
    ):
        return await call_next(request)

    return JSONResponse(
        status_code=503,
        content={"detail": "服务初始化中，请稍后重试"},
    )


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    # Add rate limit headers if available
    if hasattr(request.state, "rate_limit_remaining"):
        response.headers["X-RateLimit-Remaining"] = str(
            request.state.rate_limit_remaining
        )
        response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)

    return response


# Include the API routers
app.include_router(
    conversation.router, prefix=settings.API_V1_STR, tags=["Conversation"]
)
app.include_router(auth.router, prefix=settings.API_V1_STR, tags=["Auth"])
app.include_router(user.router, prefix=settings.API_V1_STR, tags=["User"])
app.include_router(
    personal_docs.router, prefix=settings.API_V1_STR, tags=["KnowledgeBase"]
)
app.include_router(evaluation.router, prefix=settings.API_V1_STR, tags=["Evaluation"])
app.include_router(
    llm_stats.router, prefix=settings.API_V1_STR, tags=["LLM Statistics"]
)
app.include_router(agent.router, prefix=settings.API_V1_STR, tags=["Agent"])
app.include_router(diet.router, prefix=settings.API_V1_STR, tags=["Diet"])
app.include_router(community.router, prefix=settings.API_V1_STR, tags=["Community"])
app.include_router(meta.router, prefix=settings.API_V1_STR, tags=["Meta"])
app.include_router(mcp.router, prefix=settings.API_V1_STR, tags=["MCP"])
app.include_router(events.router, prefix=settings.API_V1_STR, tags=["Events"])


@app.get("/")
async def root():
    """
    Root endpoint to check API status.
    """
    return {
        "message": "Welcome to CookHero API!",
        "db_ready": bool(getattr(app.state, "db_ready", False)),
    }
