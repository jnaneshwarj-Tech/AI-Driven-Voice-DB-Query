"""
main.py — FastAPI application entry point.
Sprint 1: Added backup, monitor routers and APScheduler for auto-backup.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import routes_auth, routes_query, routes_export, routes_files, routes_undo
import routes_backup, routes_monitor, routes_lifecycle, routes_update
from database import create_indexes, init_pool
from scheduler import start_scheduler, stop_scheduler
from security_middleware import SecurityMiddleware
from config import settings


def _expose_docs() -> bool:
    import os
    return os.getenv("API_DOCS", "").strip().lower() in ("1", "true", "yes")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup validation
    settings.validate_startup()
    init_pool()
    create_indexes()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()

app = FastAPI(
    title="AI Student Data Management System",
    description="NLP → SQL · MySQL · Role-based · File Upload · Charts · PDF · Backup & Recovery",
    version="4.0.0",
    debug=False,
    lifespan=lifespan,
    docs_url="/docs" if _expose_docs() else None,
    redoc_url="/redoc" if _expose_docs() else None,
    openapi_url="/openapi.json" if _expose_docs() else None,
)

# ── Security Middleware (Security Headers + Rate Limiting) ────────────────────
app.add_middleware(SecurityMiddleware)

# ── CORS Hardening (Restricted Origin Whitelist) ──────────────────────────────
_cors_origins = set()
for origin in (settings.ALLOWED_ORIGINS or "").split(","):
    origin_clean = origin.strip().rstrip("/")
    if origin_clean:
        _cors_origins.add(origin_clean)
if settings.FRONTEND_URL:
    _cors_origins.add(settings.FRONTEND_URL.strip().rstrip("/"))
if not _cors_origins:
    _cors_origins = {"http://localhost:5173", "http://127.0.0.1:5173"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
    max_age=600,
)

app.include_router(routes_auth.router)
app.include_router(routes_query.router)
app.include_router(routes_export.router)
app.include_router(routes_files.router)
app.include_router(routes_undo.router)
app.include_router(routes_backup.router)
app.include_router(routes_monitor.router)
app.include_router(routes_lifecycle.router)
app.include_router(routes_update.router)

@app.get("/")
def root():
    return {
        "message": "AI Student Data Management System v4.0",
        "status": "running",
        "sprint": "1 — Enterprise Database Foundation, Backup & Recovery",
    }

if __name__ == "__main__":
    import os
    import uvicorn
    dev_reload = os.getenv("DEV_RELOAD", "0").strip().lower() in ("1", "true", "yes", "on")
    uvicorn.run(
        "main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=dev_reload,
    )
