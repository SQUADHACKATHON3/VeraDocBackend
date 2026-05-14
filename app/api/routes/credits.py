from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.models.credit_purchase import CreditPurchase, CreditPurchaseStatus
from app.models.user import User
from app.schemas.credits import (
    CreditPacksOut,
    CreditPackOut,
    CreditPurchaseInitiateIn,
    CreditPurchaseInitiateOut,
)
from app.services.squad import SquadClient

router = APIRouter(prefix="/api/credits", tags=["credits"])

_PACKS = (1, 5, 10, 20)


@router.get("/packs", response_model=CreditPacksOut)
def list_packs() -> CreditPacksOut:
    unit = settings.credit_price_kobo
    return CreditPacksOut(
        packs=[CreditPackOut(credits=p, amountKobo=p * unit) for p in _PACKS],
        pricePerCreditKobo=unit,
        currency=settings.squad_currency,
    )


@router.post("/purchase/initiate", response_model=CreditPurchaseInitiateOut)
async def initiate_credit_purchase(
    payload: CreditPurchaseInitiateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditPurchaseInitiateOut:
    credits = int(payload.pack)
    if credits not in _PACKS:
        raise HTTPException(status_code=400, detail="Invalid pack. Choose 1, 5, 10, or 20 credits.")
    unit = settings.credit_price_kobo
    amount_kobo = credits * unit

    purchase = CreditPurchase(
        user_id=user.id,
        credits_granted=credits,
        amount_kobo=amount_kobo,
        status=CreditPurchaseStatus.pending,
    )
    db.add(purchase)
    db.commit()
    db.refresh(purchase)

    if not settings.squad_callback_url:
        raise HTTPException(
            status_code=503,
            detail="Squad checkout is not configured: set SQUAD_CALLBACK_URL to your frontend return URL "
            "(e.g. https://your-app.com/credits/callback). Webhooks are configured separately in the Squad dashboard "
            "to POST /api/verify/webhook on this API.",
        )

    squad = SquadClient()
    checkout_url = await squad.initiate_transaction(
        email=user.email,
        amount=amount_kobo,
        currency=settings.squad_currency,
        transaction_ref=str(purchase.id),
        callback_url=settings.squad_callback_url,
    )

    return CreditPurchaseInitiateOut(
        purchaseId=purchase.id,
        checkoutUrl=checkout_url,
        credits=credits,
        amountKobo=amount_kobo,
    )


@router.get("/purchases/{purchase_id}", response_model=dict)
def purchase_status(
    purchase_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    p = db.get(CreditPurchase, purchase_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase not found")
    return {"purchaseId": str(p.id), "status": p.status.value, "credits": p.credits_granted}
