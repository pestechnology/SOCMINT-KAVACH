"""
Shared pytest fixtures. CRITICAL: set env BEFORE importing any backend module,
so config binds to a throwaway DB and mock data mode — never the real cidecode.db.
"""
import os
import tempfile

# isolated temp DB + mock mode, set before backend.config is imported anywhere
_TMP_DB = os.path.join(tempfile.gettempdir(), "vertex_test.db")
os.environ["DB_PATH"] = _TMP_DB
os.environ["DATA_MODE"] = "mock"
os.environ["REPORT_OUTPUT_DIR"] = os.path.join(tempfile.gettempdir(), "vertex_test_reports")
os.environ["JWT_SECRET"] = "test-secret-key-for-pytest-only-not-real"
# Tests must be deterministic and offline: force the LLM into its fallback path
# (no real NVIDIA calls). Otherwise orchestrator/report tests make live network
# requests and become slow + non-deterministic.
os.environ["NVIDIA_API_KEY"] = ""

import pytest  # noqa: E402

# wipe any prior test DB so each run starts clean
for _suffix in ("", "-wal", "-shm"):
    try:
        os.remove(_TMP_DB + _suffix)
    except OSError:
        pass

import backend.config as config  # noqa: E402
config.DATA_MODE = "mock"
config.NVIDIA_API_KEY = ""  # belt-and-suspenders: keep the LLM on its fallback path
from backend.database import init_db  # noqa: E402

init_db()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from backend.main import app
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    import uuid
    u = "user_" + uuid.uuid4().hex[:8]
    r = client.post("/auth/register", json={"username": u, "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, u
