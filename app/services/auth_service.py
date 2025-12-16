"""
Authentication service for CookHero.

Provides user registration, password hashing, and JWT token generation.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database.models import UserModel
from app.database.session import get_session_context

logger = logging.getLogger(__name__)


class AuthService:
    """Service for user authentication and registration."""

    def __init__(self, secret_key: str | None = None):
        self.secret_key = secret_key or settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES

    # ------------------------------------------------------------------
    # User retrieval helpers
    # ------------------------------------------------------------------
    async def get_user_by_username(self, username: str) -> Optional[UserModel]:
        async with get_session_context() as session:
            stmt = select(UserModel).where(UserModel.username == username)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Registration & authentication
    # ------------------------------------------------------------------
    async def register_user(self, username: str, password: str) -> UserModel:
        existing = await self.get_user_by_username(username)
        if existing:
            raise ValueError("Username already exists")

        password_hash = self._hash_password(password)
        user = UserModel(username=username, password_hash=password_hash)

        async with get_session_context() as session:
            session.add(user)
            try:
                await session.flush()
            except IntegrityError as exc:
                logger.warning("Integrity error on user register: %s", exc)
                raise ValueError("Username already exists")

        logger.info("Created user %s", username)
        return user

    async def authenticate_user(self, username: str, password: str) -> Optional[UserModel]:
        user = await self.get_user_by_username(username)
        if not user:
            return None
        if not self._verify_password(password, user.password_hash):
            return None
        return user

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------
    def create_access_token(self, user: UserModel) -> str:
        expire = datetime.now() + timedelta(minutes=self.expire_minutes)
        payload = {"sub": user.username, "uid": str(user.id), "exp": expire}
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def decode_token(self, token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return {"username": payload.get("sub"), "user_id": payload.get("uid")}
        except Exception as exc:  # broad catch to avoid import of ExpiredSignatureError etc
            logger.warning("Failed to decode token: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Password helpers
    # ------------------------------------------------------------------
    def _hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def _verify_password(self, password: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except ValueError:
            return False


auth_service = AuthService()
