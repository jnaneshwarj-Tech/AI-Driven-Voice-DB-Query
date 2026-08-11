"""
main.py — FastAPI application entry point.
Sprint 1: Added backup, monitor routers and APScheduler for auto-backup.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import routes_auth, routes_query, routes_export, routes_files, routes_undo
import routes_backup, routes_monitor
from database import create_indexes, init_pool
from scheduler import start_scheduler, stop_scheduler

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
    lifespan=lifespan
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

@app.get("/")
def root():
    return {
        "message": "AI Student Data Management System v4.0",
        "status": "running",
        "sprint": "1 — Enterprise Database Foundation, Backup & Recovery",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
