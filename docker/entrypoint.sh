#!/bin/sh
# VERTEX backend container entrypoint.
# Prepares the data dir, initializes the DB + admin user (idempotent), then serves.
set -e

# Ensure the persistent data dir exists (mounted as a volume in docker-compose).
mkdir -p /data /data/reports

# Initialize / upgrade the SQLite schema. Safe to run every start.
python -m backend.database

# Create the default admin user. Guarded so an existing admin doesn't abort startup.
python -m scripts.create_admin || echo "[entrypoint] admin already exists or create skipped"

# Hand off to uvicorn (exec so it becomes PID 1 and receives signals cleanly).
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
