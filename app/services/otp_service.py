"""Create, verify, and invalidate OTP codes stored in Postgres."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.otp_code import OtpCode, OtpType


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def create_otp(
    db: Session,
    *,
    email: str,
    otp_type: OtpType,
    user_id: str | None = None,
) -> str:
    """Delete any existing OTP for this email+type, generate a new one, persist and return the plain code."""
    db.execute(
        delete(OtpCode).where(
            OtpCode.email == email,
            OtpCode.otp_type == otp_type,
        )
    )
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_ttl_minutes)
    row = OtpCode(
        user_id=user_id,
        email=email,
        otp_type=otp_type,
        code_hash=_hash_code(code),
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    return code


def get_last_otp_created_at(
    db: Session, *, email: str, otp_type: OtpType
) -> datetime | None:
    row = db.scalar(
        select(OtpCode).where(
            OtpCode.email == email, OtpCode.otp_type == otp_type
        )
    )
    return row.created_at if row else None


def verify_and_consume_otp(
    db: Session,
    *,
    email: str,
    otp_type: OtpType,
    code: str,
) -> bool:
    """Returns True and deletes the row if valid; False otherwise."""
    row = db.scalar(
        select(OtpCode).where(
            OtpCode.email == email,
            OtpCode.otp_type == otp_type,
        )
    )
    if not row:
        return False
    if row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return False
    if row.code_hash != _hash_code(code):
        return False
    db.delete(row)
    db.commit()
    return True
