from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

import routes_auth, routes_query, routes_files, routes_export
from database_connection import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="AI College DB Query System (MySQL)",
    version="1.0.0",
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
app.include_router(routes_files.router)
app.include_router(routes_export.router)

@app.get("/")
def root():
    return {"message": "AI MySQL Query System running.", "version": "1.0.0"}
