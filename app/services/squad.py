import hashlib
import hmac
from typing import Any

import httpx

from app.core.config import settings


class SquadClient:
    def __init__(self) -> None:
        self.base_url = settings.squad_base_url.rstrip("/")

    async def initiate_transaction(self, *, email: str, amount: int, currency: str, transaction_ref: str, callback_url: str) -> str:
        url = f"{self.base_url}/transaction/initiate"
        headers = {"Authorization": f"Bearer {settings.squad_secret_key}", "Content-Type": "application/json"}
        payload = {
            "email": email,
            "amount": amount,
            "currency": currency,
            # Squad's initiate endpoint expects this in many integrations.
            "initiate_type": "inline",
            "transaction_ref": transaction_ref,
            "callback_url": callback_url,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        checkout_url = data.get("data", {}).get("checkout_url")
        if not checkout_url:
            raise RuntimeError("Squad initiate did not return checkout_url")
        return checkout_url

    async def verify_transaction(self, *, transaction_ref: str) -> dict[str, Any]:
        # Squad verify endpoint is commonly exposed as:
        # GET /transaction/verify/{transaction_ref}
        url = f"{self.base_url}/transaction/verify/{transaction_ref}"
        headers = {"Authorization": f"Bearer {settings.squad_secret_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()


def compute_squad_signature(raw_body: bytes) -> str:
    # Squad webhook signatures are computed using the Secret Key
    # (no separate webhook secret in many setups).
    secret = settings.squad_secret_key.encode("utf-8")
    return hmac.new(secret, raw_body, hashlib.sha512).hexdigest()


def verify_squad_signature(raw_body: bytes, provided_signature: str | None) -> bool:
    if not provided_signature:
        return False
    expected = compute_squad_signature(raw_body)
    return hmac.compare_digest(expected, provided_signature)

