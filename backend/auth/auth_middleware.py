"""
backend/auth/auth_middleware.py — FastAPI dependency to protect routes.

Usage:
    from backend.auth.auth_middleware import get_current_user
    @router.get("/thing")
    def thing(user_id: str = Depends(get_current_user)): ...
"""
from __future__ import annotations

from fastapi import Header, HTTPException

from backend.auth.auth_service import decode_token


def get_current_user(authorization: str = Header(default="")) -> str:
    """Decode 'Authorization: Bearer <token>' -> user_id, else 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing token in Authorization header")
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


def get_current_user_optional(authorization: str = Header(default="")) -> str | None:
    """Decode 'Authorization: Bearer <token>' -> user_id if valid, else return None without raising 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None
    return decode_token(token)
