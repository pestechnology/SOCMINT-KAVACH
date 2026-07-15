"""tests/test_auth_middleware.py — unit tests for get_current_user and get_current_user_optional."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from backend.auth.auth_middleware import get_current_user, get_current_user_optional


def test_get_current_user_valid(monkeypatch):
    monkeypatch.setattr("backend.auth.auth_middleware.decode_token", lambda token: "user-123" if token == "valid-token" else None)
    user_id = get_current_user(authorization="Bearer valid-token")
    assert user_id == "user-123"


def test_get_current_user_missing_or_malformed():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="Basic foobar")
    assert exc_info.value.status_code == 401
    assert "Missing or malformed Authorization header" in exc_info.value.detail

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="")
    assert exc_info.value.status_code == 401


def test_get_current_user_empty_token():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="Bearer   ")
    assert exc_info.value.status_code == 401
    assert "Missing token" in exc_info.value.detail


def test_get_current_user_invalid_token(monkeypatch):
    monkeypatch.setattr("backend.auth.auth_middleware.decode_token", lambda token: None)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="Bearer expired-or-bad")
    assert exc_info.value.status_code == 401
    assert "Invalid or expired token" in exc_info.value.detail


def test_get_current_user_optional(monkeypatch):
    monkeypatch.setattr("backend.auth.auth_middleware.decode_token", lambda token: "user-abc" if token == "good-token" else None)
    assert get_current_user_optional(authorization="Bearer good-token") == "user-abc"
    assert get_current_user_optional(authorization="Bearer bad-token") is None
    assert get_current_user_optional(authorization="Basic xxx") is None
    assert get_current_user_optional(authorization="") is None
