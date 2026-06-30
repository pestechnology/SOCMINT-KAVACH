"""
backend/auth/auth_routes.py — POST /auth/register, POST /auth/login, GET /auth/me
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth.auth_middleware import get_current_user
from backend.auth.auth_service import authenticate, create_token, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str
    password: str


@router.post("/register")
def register(body: Credentials):
    try:
        user_id = register_user(body.username, body.password)
    except ValueError as e:
        # Duplicate username is a genuine conflict (409); a too-short
        # username/password is a client validation error (400).
        status = 409 if "exists" in str(e).lower() else 400
        raise HTTPException(status_code=status, detail=str(e))
    return {"user_id": user_id, "token": create_token(user_id)}


@router.post("/login")
def login(body: Credentials):
    user = authenticate(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": create_token(user["user_id"]), "user": user}


@router.get("/me")
def me(user_id: str = Depends(get_current_user)):
    return {"user_id": user_id}
