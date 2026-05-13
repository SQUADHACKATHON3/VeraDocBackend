from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import jwt

from app.core.config import settings

def hash_password(password: str) -> str:
    pw_bytes = password.encode("utf-8")
    # bcrypt only uses first 72 bytes; enforce to avoid surprises.
    if len(pw_bytes) > 72:
        pw_bytes = pw_bytes[:72]
    hashed = bcrypt.hashpw(pw_bytes, bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    pw_bytes = plain_password.encode("utf-8")
    if len(pw_bytes) > 72:
        pw_bytes = pw_bytes[:72]
    return bcrypt.checkpw(pw_bytes, hashed_password.encode("utf-8"))


def create_access_token(subject: str, *, expires_minutes: int | None = None, extra: dict[str, Any] | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes if expires_minutes is not None else settings.jwt_access_token_expires_minutes
    )
    payload: dict[str, Any] = {"sub": subject, "type": "access", "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_refresh_token(subject: str, *, expires_days: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=expires_days if expires_days is not None else settings.jwt_refresh_token_expires_days
    )
    payload: dict[str, Any] = {"sub": subject, "type": "refresh", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

