import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import jwt  # type: ignore[import-untyped]
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)  # type: ignore[no-any-return]


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)  # type: ignore[no-any-return]


def create_access_token(user_id: str, org_id: str, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )  # type: ignore[no-any-return]


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(  # type: ignore[no-any-return]
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )


def make_refresh_token_id() -> str:
    return str(uuid.uuid4())


def refresh_token_redis_key(token_id: str) -> str:
    return f"refresh:{token_id}"
