import hashlib
import hmac
from typing import Any

import httpx
from django.conf import settings


class SquadClient:
    def __init__(self) -> None:
        self.base_url = settings.SQUAD_BASE_URL.rstrip("/")

    def initiate_transaction(
        self, *, email: str, amount: int, currency: str, transaction_ref: str, callback_url: str
    ) -> str:
        url = f"{self.base_url}/transaction/initiate"
        headers = {"Authorization": f"Bearer {settings.SQUAD_SECRET_KEY}", "Content-Type": "application/json"}
        payload = {
            "email": email,
            "amount": amount,
            "currency": currency,
            "initiate_type": "inline",
            "transaction_ref": transaction_ref,
            "callback_url": callback_url,
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        checkout_url = data.get("data", {}).get("checkout_url")
        if not checkout_url:
            raise RuntimeError("Squad initiate did not return checkout_url")
        return checkout_url

    def verify_transaction(self, *, transaction_ref: str) -> dict[str, Any]:
        url = f"{self.base_url}/transaction/verify/{transaction_ref}"
        headers = {"Authorization": f"Bearer {settings.SQUAD_SECRET_KEY}", "Content-Type": "application/json"}
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()


def _squad_verify_data(verify_resp: dict[str, Any]) -> dict[str, Any]:
    data = verify_resp.get("data")
    if not isinstance(data, dict):
        data = verify_resp if isinstance(verify_resp, dict) else {}
    return data


def squad_verify_response_indicates_success(verify_resp: dict[str, Any]) -> bool:
    status_value = _squad_verify_data(verify_resp).get("transaction_status")
    return str(status_value).lower() == "success"


def squad_verify_amount_kobo(verify_resp: dict[str, Any]) -> int | None:
    raw = _squad_verify_data(verify_resp).get("amount")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def squad_payment_matches_purchase(verify_resp: dict[str, Any], *, expected_kobo: int) -> bool:
    if not squad_verify_response_indicates_success(verify_resp):
        return False
    paid = squad_verify_amount_kobo(verify_resp)
    return paid is not None and paid == expected_kobo


def squad_webhook_hmac_hex_upper(raw_body: bytes) -> str:
    secret = settings.SQUAD_SECRET_KEY.encode("utf-8")
    return hmac.new(secret, raw_body, hashlib.sha512).hexdigest().upper()


def verify_squad_webhook_authentic(
    raw_body: bytes,
    *,
    encrypted_body_header: str | None,
    legacy_signature_header: str | None,
) -> bool:
    if encrypted_body_header:
        expected = squad_webhook_hmac_hex_upper(raw_body)
        return hmac.compare_digest(expected, encrypted_body_header.strip().upper())
    if legacy_signature_header:
        secret = settings.SQUAD_SECRET_KEY.encode("utf-8")
        digest = hmac.new(secret, raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(digest, legacy_signature_header.strip())
    return False
