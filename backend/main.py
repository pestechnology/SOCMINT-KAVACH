"""VERTEX FastAPI application — entry point for the API server."""

import logging
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import settings
from backend.database.db import init_db
from backend.orchestrator import run_investigation
from backend.schemas import Identifier, IdentifierType

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Request / Response schemas ───────────────────────────────────────
class InvestigateRequest(BaseModel):
    """Incoming investigation seed."""

    type: str
    value: str


class InvestigateResponse(BaseModel):
    """Investigation result with profiles and clusters."""

    status: str
    profile_count: int
    profiles: list[dict[str, Any]]
    cluster_count: int
    clusters: list[dict[str, Any]]


# ── Lifespan ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: init DB. Shutdown: nothing yet."""
    logger.info("VERTEX starting — DATA_MODE=%s", settings.DATA_MODE)
    init_db(settings.DB_PATH)
    yield
    logger.info("VERTEX shutting down")


# ── App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="VERTEX",
    description="SOCMINT/OSINT suspect profiling tool",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ───────────────────────────────────────────────────────────
@app.post("/investigate", response_model=InvestigateResponse)
async def investigate(req: InvestigateRequest) -> InvestigateResponse:
    """Run the full investigation pipeline: scrape → correlate → score."""
    # Validate identifier type against the enum
    try:
        id_type = IdentifierType(req.type)
    except ValueError:
        valid = [t.value for t in IdentifierType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid identifier type '{req.type}'. Valid types: {valid}",
        )

    identifier = Identifier(type=id_type, value=req.value)

    t0 = time.perf_counter()
    profiles, clusters = await run_investigation(identifier)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    logger.info(
        "Investigate complete: type=%s value=%s profiles=%d clusters=%d elapsed=%.1fms",
        req.type,
        req.value,
        len(profiles),
        len(clusters),
        elapsed_ms,
    )

    return InvestigateResponse(
        status="complete",
        profile_count=len(profiles),
        profiles=[asdict(p) for p in profiles],
        cluster_count=len(clusters),
        clusters=[asdict(c) for c in clusters],
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok", "data_mode": settings.DATA_MODE}
