"""
FastAPI application entrypoint.

Initialises the database pool, K8s client, session middleware,
and registers all routers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.debug_log import write_debug_log
from app.utils.k8s_utils import init_k8s_client

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log_level = logging.DEBUG if settings.DEBUG else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Billing background worker
# ---------------------------------------------------------------------------

async def _billing_worker(app: FastAPI) -> None:
    from app.config import build_vm_pricing
    from app.services.billing_loop import billing_tick, stop_all_user_vms

    pricing = build_vm_pricing(settings)

    while True:
        await asyncio.sleep(settings.BILLING_INTERVAL_SECONDS)
        try:
            db = app.state.db
            if db is None:
                continue
            kill_list = await billing_tick(db, pricing)
            for user_id in kill_list:
                n = await stop_all_user_vms(db, user_id)
                logger.info(
                    "Billing: stopped %d VMs for user %d (insufficient funds)",
                    n, user_id,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Billing tick failed")


# ---------------------------------------------------------------------------
# Lifespan: DB pool + K8s client + global network policy
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- K8s client ---
    if not init_k8s_client():
        logger.critical("Failed to initialise Kubernetes client")
        raise SystemExit("Unable to load Kubernetes configuration")

    # --- Global network policy ---
    if not settings.FRONTEND_STUB_MODE:
        try:
            from app.utils.network_policy_utils import create_vm_global_network_policy

            cidrs = [c for c in settings.SERVER_NETWORK_CIDRS if c]
            create_vm_global_network_policy(
                settings.POD_NETWORK_CIDR, settings.SERVICE_NETWORK_CIDR, cidrs,
            )
            logger.info("GlobalNetworkPolicy initialised")
        except Exception as e:
            logger.warning("GlobalNetworkPolicy setup failed: %s (continuing)", e)

    # --- LLM service (chat + available-models via /v1/models) ---
    if settings.LLM_SERVICE_URL:
        logger.info(
            "LLM service: %s",
            settings.LLM_SERVICE_URL,
        )
        if not settings.LLM_CHAT_SHARED_TOKEN:
            logger.warning("LLM chat shared token is not configured (LLM_CHAT_SHARED_TOKEN)")
    else:
        logger.warning("LLM service: LLM_SERVICE_URL empty — LLM features unavailable")

    # --- Database ---
    db = None
    if settings.DATABASE_URL:
        import bcrypt

        from app.database import create_db

        async with create_db(settings.DATABASE_URL) as db:
            app.state.db = db
            logger.info("Database pool ready")

            # Bootstrap: create first admin if no users exist
            if settings.ADMIN_USERNAME and settings.ADMIN_PASSWORD:
                users = await db.users.list_all(include_inactive=True)
                if not users:
                    pw_hash = bcrypt.hashpw(
                        settings.ADMIN_PASSWORD.encode("utf-8"),
                        bcrypt.gensalt(),
                    ).decode("utf-8")
                    admin = await db.users.create_user(
                        settings.ADMIN_USERNAME,
                        pw_hash,
                        role="admin",
                    )
                    logger.info("Created bootstrap admin user: %s (id=%s)", admin.username, admin.id)

            # Billing background task
            billing_task: asyncio.Task | None = None
            if settings.BILLING_ENABLED:
                billing_task = asyncio.create_task(
                    _billing_worker(app), name="billing-worker",
                )
                logger.info(
                    "Billing worker started (interval=%ds)",
                    settings.BILLING_INTERVAL_SECONDS,
                )

            yield

            if billing_task is not None:
                billing_task.cancel()
                try:
                    await billing_task
                except asyncio.CancelledError:
                    pass
                logger.info("Billing worker stopped")
    else:
        logger.warning("DATABASE_URL not set — running without persistence")
        app.state.db = None
        yield


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Viirtuoz VPS",
    version="2.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def agent_llm_route_trace(request: Request, call_next):
    path = request.url.path
    is_llm_flow = path.startswith("/adm/llm") or path.endswith("/llm/chat")
    if is_llm_flow:
        # region agent log
        write_debug_log(
            run_id="run1",
            hypothesis_id="H2",
            location="app/main.py:agent_llm_route_trace:entry",
            message="llm request entered app",
            data={"method": request.method, "path": path},
        )
        # endregion

    response = await call_next(request)

    if is_llm_flow:
        # region agent log
        write_debug_log(
            run_id="run1",
            hypothesis_id="H2",
            location="app/main.py:agent_llm_route_trace:exit",
            message="llm request completed",
            data={"method": request.method, "path": path, "status_code": response.status_code},
        )
        # endregion
    return response

# Disable cache for HTML in debug mode (avoid stale UI)
if settings.DEBUG:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    @app.middleware("http")
    async def no_cache_html(request: Request, call_next):
        response = await call_next(request)
        if "text/html" in response.headers.get("content-type", ""):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

# Signed-cookie sessions (replaces Flask server-side sessions)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=settings.SESSION_TIMEOUT,
    same_site="lax",
    session_cookie="session",
)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ---------------------------------------------------------------------------
# Health / readiness
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"])
async def health():
    """Health check. Includes app version to verify deployed code."""
    return {"status": "healthy", "version": app.version}


@app.get("/ready", tags=["ops"])
async def ready():
    if settings.FRONTEND_STUB_MODE:
        return {"status": "ready", "mode": "stub"}
    try:
        from app.utils.k8s_utils import get_core_api
        from app.utils.async_helpers import run_sync

        api = get_core_api()
        await run_sync(api.list_namespace, limit=1)
        return {"status": "ready"}
    except Exception as e:
        logger.error("Readiness check failed: %s", e)
        return {"status": "not ready", "error": str(e)}, 503


# ---------------------------------------------------------------------------
# Login page (Jinja2 template, for backward compat)
# ---------------------------------------------------------------------------

from fastapi import Request
from fastapi.responses import HTMLResponse
from app.templating import Jinja2Templates

_templates = Jinja2Templates(directory="app/templates")


def _is_api_request_path(path: str) -> bool:
    return (
        path.startswith("/api/")
        or path.startswith("/admin/api/")
        or path.startswith("/auth/")
        or path.startswith("/health")
        or path.startswith("/ready")
        or "/api/" in path
    )


def _prefers_html(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "text/html" in accept


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    path = request.url.path
    if _is_api_request_path(path) or not _prefers_html(request):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    return _templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": exc.status_code,
            "error_title": "Something went wrong",
            "error_message": str(exc.detail) if exc.detail else "Unexpected request error",
            "error_path": path,
        },
        status_code=exc.status_code,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error for path %s: %s", request.url.path, exc)
    path = request.url.path
    if _is_api_request_path(path) or not _prefers_html(request):
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    return _templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": 500,
            "error_title": "Server error",
            "error_message": "Please try again or contact support if the issue persists.",
            "error_path": path,
        },
        status_code=500,
    )


@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    return _templates.TemplateResponse("login.html", {"request": request})


@app.get("/logout", include_in_schema=False)
async def logout_redirect(request: Request):
    """Logout: clear session and redirect to login."""
    from fastapi.responses import RedirectResponse
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------

from app.routers import admin, auth, dashboard, llm, storage, vm_details, vms

app.include_router(auth.router, prefix="/auth")
app.include_router(admin.router)
app.include_router(dashboard.router)
app.include_router(vms.router)
app.include_router(vm_details.router)
app.include_router(storage.router)
app.include_router(llm.router)

if __name__ == "__main__":
    import uvicorn

    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "8080"))
    workers = 1
    log_level = os.environ.get("LOG_LEVEL", "info").lower()

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        workers=workers,
        log_level=log_level,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
