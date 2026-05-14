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


def squad_webhook_hmac_hex_upper(raw_body: bytes) -> str:
    """HMAC-SHA512 of raw webhook body, hex uppercase (Squad `x-squad-encrypted-body`)."""
    secret = settings.squad_secret_key.encode("utf-8")
    return hmac.new(secret, raw_body, hashlib.sha512).hexdigest().upper()


def verify_squad_webhook_authentic(
    raw_body: bytes,
    *,
    encrypted_body_header: str | None,
    legacy_signature_header: str | None,
) -> bool:
    """
    Squad docs: compare HMAC-SHA512(secret, raw_body) as **uppercase** hex to `x-squad-encrypted-body`.
    We also accept legacy `x-squad-signature` as lowercase hex for older integrations.
    """
    if encrypted_body_header:
        expected = squad_webhook_hmac_hex_upper(raw_body)
        try:
            return hmac.compare_digest(expected, encrypted_body_header.strip().upper())
        except (TypeError, ValueError):
            return False

    if legacy_signature_header:
        secret = settings.squad_secret_key.encode("utf-8")
        expected_lower = hmac.new(secret, raw_body, hashlib.sha512).hexdigest().lower()
        try:
            return hmac.compare_digest(expected_lower, legacy_signature_header.strip().lower())
        except (TypeError, ValueError):
            return False

    return False

