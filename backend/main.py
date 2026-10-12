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


def _expose_docs() -> bool:
    import os
    return os.getenv("API_DOCS", "").strip().lower() in ("1", "true", "yes")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
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
    lifespan=lifespan,
    # The generated schema lists every door and payload in the system. That is a
    # developer tool, not something college staff use, so it stays closed in a
    # deployment; start with API_DOCS=1 to open /docs and /openapi.json again.
    docs_url="/docs" if _expose_docs() else None,
    redoc_url="/redoc" if _expose_docs() else None,
    openapi_url="/openapi.json" if _expose_docs() else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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
    # Dev convenience is preserved (auto-reload on), but the bind host, port and
    # reload are now env-driven so production can start cleanly without editing
    # code: set DEV_RELOAD=0 (and a proper host/port) behind a real ASGI server.
    dev_reload = os.getenv("DEV_RELOAD", "1").strip().lower() in ("1", "true", "yes", "on")
    uvicorn.run(
        "main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=dev_reload,
    )
