"""
backend/auth/auth_service.py — registration, login, JWT issue/verify.

    register_user(username, password) -> user_id
    authenticate(username, password)  -> user dict | None
    create_token(user_id)             -> jwt str
    decode_token(token)               -> user_id | None

Passwords are bcrypt-hashed; plaintext is never stored or logged.
"""
from __future__ import annotations

import datetime
import uuid

import bcrypt
from jose import jwt

from backend import config
from backend.database import get_db

_ALGO = "HS256"


# bcrypt only considers the first 72 bytes and modern versions RAISE on longer
# input. Truncate consistently on both hash and check so a long password can
# never crash registration or cause an inconsistent login.
def _hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def _check_pw(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except Exception:
        return False


def register_user(username: str, password: str, role: str = "investigator") -> str:
    username = (username or "").strip()
    if len(username) < 3:
        raise ValueError("username must be at least 3 characters")
    if len(password or "") < 6:
        raise ValueError("password must be at least 6 characters")
    conn = get_db()
    try:
        existing = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            raise ValueError("username already exists")
        user_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO users (user_id, username, password_hash, role, created_at) VALUES (?,?,?,?,?)",
            (user_id, username, _hash_pw(password), role,
             datetime.datetime.now(datetime.timezone.utc).isoformat()),
        )
        conn.commit()
        return user_id
    finally:
        conn.close()


def authenticate(username: str, password: str) -> dict | None:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    finally:
        conn.close()
    if row and _check_pw(password, row["password_hash"]):
        return {"user_id": row["user_id"], "username": row["username"], "role": row["role"]}
    return None


def create_token(user_id: str) -> str:
    expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        hours=config.TOKEN_EXPIRY_HOURS)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, config.JWT_SECRET, algorithm=_ALGO)


def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[_ALGO])
        return payload.get("sub")
    except Exception:
        # JWTError covers bad signature/expiry, but a malformed token can also
        # raise other exceptions; any failure means "not authenticated" (401),
        # never a 500 with a leaked stack trace.
        return None
