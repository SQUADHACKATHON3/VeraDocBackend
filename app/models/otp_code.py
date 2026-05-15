import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OtpType(str, enum.Enum):
    email_verification = "email_verification"
    password_reset = "password_reset"


class OtpCode(Base):
    __tablename__ = "otp_codes"
    __table_args__ = (UniqueConstraint("email", "otp_type", name="uq_otp_codes_email_type"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    """Null only for password_reset flow before the user row is resolved."""
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    otp_type: Mapped[OtpType] = mapped_column(Enum(OtpType, name="otptype"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    """SHA-256 hex digest of the 6-digit code."""
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
