from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import routes_auth, routes_query, routes_export, routes_files
from database import create_indexes, init_pool

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    create_indexes()
    yield

app = FastAPI(
    title="AI Student Data Management System",
    description="NLP → SQL · MySQL · Role-based · File Upload · Charts · PDF",
    version="3.0.0",
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

@app.get("/")
def root():
    return {"message": "AI Student Data Management System v3.0", "status": "running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
