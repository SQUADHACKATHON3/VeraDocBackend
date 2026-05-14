import uuid
from typing import Literal

from pydantic import BaseModel


class CreditPackOut(BaseModel):
    credits: int
    amountKobo: int


class CreditPacksOut(BaseModel):
    packs: list[CreditPackOut]
    pricePerCreditKobo: int
    currency: str = "NGN"


class CreditPurchaseInitiateIn(BaseModel):
    pack: Literal[1, 5, 10, 20]


class CreditPurchaseInitiateOut(BaseModel):
    purchaseId: uuid.UUID
    checkoutUrl: str
    credits: int
    amountKobo: int


class CreditPurchaseStatusOut(BaseModel):
    purchaseId: uuid.UUID
    status: str
    credits: int


class CreditPurchaseVerifyOut(CreditPurchaseStatusOut):
    """Response from POST /purchases/{id}/verify."""

    paymentConfirmed: bool | None = None
    """True if Squad reports success and purchase is completed; False if still pending or not paid yet."""

    alreadyCompleted: bool = False
    """True if this purchase was already completed before this call (no Squad verify needed)."""
