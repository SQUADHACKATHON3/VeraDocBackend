"""Finalize Squad-backed credit purchases (shared by webhook and POST /purchases/.../verify)."""

from uuid import UUID

from django.db import transaction

from accounts.models import User
from credits.models import CreditPurchase, CreditPurchaseStatus


@transaction.atomic
def complete_pending_credit_purchase_by_id(purchase_id: UUID) -> CreditPurchase | None:
    purchase = (
        CreditPurchase.objects.select_for_update()
        .filter(id=purchase_id, status=CreditPurchaseStatus.PENDING)
        .first()
    )
    if not purchase:
        return CreditPurchase.objects.filter(id=purchase_id).first()

    owner = User.objects.select_for_update().filter(id=purchase.user_id).first()
    if not owner:
        return purchase

    owner.credits += purchase.credits_granted
    owner.save(update_fields=["credits"])
    purchase.status = CreditPurchaseStatus.COMPLETED
    purchase.save(update_fields=["status"])
    return purchase
