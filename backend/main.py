"""
backend/main.py — FastAPI entrypoint for VERTEX.

Run:  uvicorn backend.main:app --reload
Routers (auth, cases, ...) are wired in as later agents add them.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import config
from backend.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    config.validate_keys()
    yield


app = FastAPI(title="VERTEX", description="SOCMINT/OSINT suspect-profiling API",
              version="0.1.0", lifespan=lifespan)

# Auth uses Bearer tokens (not cookies), so credentials are not needed — and
# allow_origins=["*"] WITH allow_credentials=True is an invalid combo browsers reject.
# Origins are configurable via CORS_ORIGINS (comma-separated); defaults to the local UI.
import os as _os
_origins = [o.strip() for o in _os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "data_mode": config.DATA_MODE}


# ---- Routers (added by later agents) ----
try:
    from backend.auth.auth_routes import router as auth_router
    app.include_router(auth_router)
except Exception as e:  # ASCII only — Windows console is cp1252
    print(f"[main] WARNING: auth routes failed to load: {e}")

try:
    from backend.cases.case_routes import router as case_router
    app.include_router(case_router)
except Exception as e:
    print(f"[main] WARNING: case routes failed to load: {e}")
