import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CreditPurchaseStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class CreditPurchase(Base):
    __tablename__ = "credit_purchases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    credits_granted: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_kobo: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[CreditPurchaseStatus] = mapped_column(
        Enum(CreditPurchaseStatus, name="creditpurchasestatus"),
        default=CreditPurchaseStatus.pending,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="credit_purchases")
