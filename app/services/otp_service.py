"""Create, verify, and invalidate OTP codes stored in Postgres."""

from __future__ import annotations

import enum
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.otp_code import OtpCode, OtpType


class OtpVerifyResult(str, enum.Enum):
    ok = "ok"
    invalid = "invalid"
    expired = "expired"
    locked = "locked"


def _hash_code(code: str) -> str:
    pepper = settings.jwt_secret.encode("utf-8")
    return hmac.new(pepper, code.encode(), hashlib.sha256).hexdigest()


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
        failed_attempts=0,
    )
    db.add(row)
    db.commit()
    return code


def get_last_otp_created_at(
    db: Session, *, email: str, otp_type: OtpType
) -> datetime | None:
    row = db.scalar(
        select(OtpCode).where(
            OtpCode.email == email,
            OtpCode.otp_type == otp_type,
        )
    )
    return row.created_at if row else None


def verify_and_consume_otp(
    db: Session,
    *,
    email: str,
    otp_type: OtpType,
    code: str,
) -> OtpVerifyResult:
    row = db.scalar(
        select(OtpCode).where(
            OtpCode.email == email,
            OtpCode.otp_type == otp_type,
        )
    )
    if not row:
        return OtpVerifyResult.invalid

    now = datetime.now(timezone.utc)
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if expires < now:
        db.delete(row)
        db.commit()
        return OtpVerifyResult.expired

    if row.failed_attempts >= settings.otp_max_attempts:
        db.delete(row)
        db.commit()
        return OtpVerifyResult.locked

    if not hmac.compare_digest(row.code_hash, _hash_code(code)):
        row.failed_attempts += 1
        if row.failed_attempts >= settings.otp_max_attempts:
            db.delete(row)
            db.commit()
            return OtpVerifyResult.locked
        db.add(row)
        db.commit()
        return OtpVerifyResult.invalid

    db.delete(row)
    db.commit()
    return OtpVerifyResult.ok
