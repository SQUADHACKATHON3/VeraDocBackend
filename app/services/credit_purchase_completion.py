"""Finalize Squad-backed credit purchases (shared by webhook and client reconcile)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.credit_purchase import CreditPurchase, CreditPurchaseStatus
from app.models.user import User


def complete_pending_credit_purchase_by_id(db: Session, purchase_id: UUID) -> CreditPurchase | None:
    """
    Row-lock a pending purchase, grant credits, mark completed.
    Returns the purchase row after commit (completed or unchanged if not pending).
    """
    p = db.scalar(
        select(CreditPurchase)
        .where(
            CreditPurchase.id == purchase_id,
            CreditPurchase.status == CreditPurchaseStatus.pending,
        )
        .with_for_update()
    )
    if not p:
        return db.get(CreditPurchase, purchase_id)

    owner = db.scalar(select(User).where(User.id == p.user_id).with_for_update())
    if not owner:
        db.commit()
        return db.get(CreditPurchase, purchase_id)

    owner.credits += p.credits_granted
    p.status = CreditPurchaseStatus.completed
    db.add(owner)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p
