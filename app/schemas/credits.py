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
