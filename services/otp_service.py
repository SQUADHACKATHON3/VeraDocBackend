"""Create, verify, and invalidate OTP codes stored in Postgres."""

from __future__ import annotations

import enum
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.db import transaction

from common.models import OtpCode, OtpType


class OtpVerifyResult(str, enum.Enum):
    ok = "ok"
    invalid = "invalid"
    expired = "expired"
    locked = "locked"


def _hash_code(code: str) -> str:
    pepper = settings.JWT_SECRET.encode("utf-8")
    return hmac.new(pepper, code.encode(), hashlib.sha256).hexdigest()


def create_otp(
    *,
    email: str,
    otp_type: str,
    user_id: str | None = None,
) -> str:
    OtpCode.objects.filter(email=email, otp_type=otp_type).delete()
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_TTL_MINUTES)
    OtpCode.objects.create(
        user_id=user_id,
        email=email,
        otp_type=otp_type,
        code_hash=_hash_code(code),
        expires_at=expires_at,
        failed_attempts=0,
    )
    return code


def get_last_otp_created_at(*, email: str, otp_type: str) -> datetime | None:
    row = OtpCode.objects.filter(email=email, otp_type=otp_type).order_by("-created_at").first()
    return row.created_at if row else None


@transaction.atomic
def verify_and_consume_otp(*, email: str, otp_type: str, code: str) -> OtpVerifyResult:
    row = OtpCode.objects.filter(email=email, otp_type=otp_type).select_for_update().first()
    if not row:
        return OtpVerifyResult.invalid

    now = datetime.now(timezone.utc)
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        row.delete()
        return OtpVerifyResult.expired

    if row.failed_attempts >= settings.OTP_MAX_ATTEMPTS:
        row.delete()
        return OtpVerifyResult.locked

    if not hmac.compare_digest(row.code_hash, _hash_code(code)):
        row.failed_attempts += 1
        if row.failed_attempts >= settings.OTP_MAX_ATTEMPTS:
            row.delete()
            return OtpVerifyResult.locked
        row.save(update_fields=["failed_attempts"])
        return OtpVerifyResult.invalid

    row.delete()
    return OtpVerifyResult.ok
