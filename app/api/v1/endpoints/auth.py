"""
Authentication API endpoints: register and login.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.auth_service import auth_service

router = APIRouter()
logger = logging.getLogger(__name__)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=3, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=3, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


@router.post("/auth/register", response_model=TokenResponse)
async def register(request: RegisterRequest):
    """Register a new user with hashed password."""
    try:
        user = await auth_service.register_user(request.username, request.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Register error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Registration failed")

    token = auth_service.create_access_token(user)
    return TokenResponse(access_token=token, username=user.username)


@router.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Authenticate user and return JWT token."""
    user = await auth_service.authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    token = auth_service.create_access_token(user)
    return TokenResponse(access_token=token, username=user.username)
