"""
scripts/create_admin.py — create (or reset) an admin user.

Usage:
    python -m scripts.create_admin                       # uses defaults below
    python -m scripts.create_admin <username> <password> # custom

Idempotent: if the user already exists, its password + role are reset.
"""
from __future__ import annotations

import datetime
import sys
import uuid

import bcrypt

from backend.database import get_db, init_db

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "vertex2026"


def create_admin(username: str, password: str) -> None:
    init_db()
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_db()
    try:
        row = conn.execute("SELECT user_id FROM users WHERE username = ?", (username,)).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET password_hash = ?, role = 'admin' WHERE username = ?",
                (pw_hash, username),
            )
            action = "reset"
        else:
            conn.execute(
                "INSERT INTO users (user_id, username, password_hash, role, created_at) VALUES (?,?,?,?,?)",
                (uuid.uuid4().hex, username, pw_hash, "admin", now),
            )
            action = "created"
        conn.commit()
    finally:
        conn.close()
    print(f"Admin {action}: username='{username}' role='admin'")


if __name__ == "__main__":
    u = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_USERNAME
    p = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PASSWORD
    create_admin(u, p)
