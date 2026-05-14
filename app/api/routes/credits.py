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
    CreditPurchaseStatusOut,
    CreditPurchaseVerifyOut,
)
from app.services.credit_purchase_completion import complete_pending_credit_purchase_by_id
from app.services.squad import SquadClient, squad_verify_response_indicates_success

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


@router.post("/purchases/{purchase_id}/verify", response_model=CreditPurchaseVerifyOut)
async def verify_credit_purchase(
    purchase_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditPurchaseVerifyOut:
    """
    Ask Squad whether this purchase was paid, then grant credits if so.
    Same outcome as the Squad webhook when it fires; use after redirect from checkout if polling status.
    """
    p = db.get(CreditPurchase, purchase_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase not found")

    if p.status == CreditPurchaseStatus.completed:
        return CreditPurchaseVerifyOut(
            purchaseId=p.id,
            status=p.status.value,
            credits=p.credits_granted,
            alreadyCompleted=True,
            paymentConfirmed=True,
        )

    if p.status == CreditPurchaseStatus.failed:
        raise HTTPException(status_code=400, detail="This purchase failed; start a new checkout.")

    try:
        squad = SquadClient()
        verify_resp = await squad.verify_transaction(transaction_ref=str(purchase_id))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Squad verify request failed: {e!s}") from e

    if not squad_verify_response_indicates_success(verify_resp):
        return CreditPurchaseVerifyOut(
            purchaseId=p.id,
            status=p.status.value,
            credits=p.credits_granted,
            paymentConfirmed=False,
            alreadyCompleted=False,
        )

    p2 = complete_pending_credit_purchase_by_id(db, purchase_id)
    p_final = p2 or db.get(CreditPurchase, purchase_id)
    if not p_final:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase not found")

    return CreditPurchaseVerifyOut(
        purchaseId=p_final.id,
        status=p_final.status.value,
        credits=p_final.credits_granted,
        paymentConfirmed=p_final.status == CreditPurchaseStatus.completed,
        alreadyCompleted=False,
    )


@router.get("/purchases/{purchase_id}", response_model=CreditPurchaseStatusOut)
def purchase_status(
    purchase_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditPurchaseStatusOut:
    p = db.get(CreditPurchase, purchase_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase not found")
    return CreditPurchaseStatusOut(
        purchaseId=p.id,
        status=p.status.value,
        credits=p.credits_granted,
    )
