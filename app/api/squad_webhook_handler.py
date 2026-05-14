"""Shared Squad payment webhook logic (credit purchases + legacy per-verification pay)."""

import json
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.credit_purchase import CreditPurchase, CreditPurchaseStatus
from app.models.user import User
from app.models.verification import PaymentStatus, Verification, VerificationStatus
from app.models.webhook_event import WebhookEvent
from app.services.squad import SquadClient, verify_squad_signature
from app.tasks.verification_tasks import process_verification


async def handle_squad_charge_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session,
) -> dict:
    raw = await request.body()
    sig = request.headers.get("x-squad-signature")
    sig_valid = verify_squad_signature(raw, sig)
    if not sig_valid:
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = payload.get("Event")
    body = payload.get("Body") or {}
    transaction_ref = body.get("transaction_ref")
    idem_key = f"squad:{event}:{transaction_ref}"

    existing = db.scalar(select(WebhookEvent).where(WebhookEvent.idempotency_key == idem_key))
    if existing:
        return {"received": True}

    db.add(
        WebhookEvent(
            provider="squad",
            event_type=str(event),
            idempotency_key=idem_key,
            signature_valid=True,
            raw_payload=raw.decode("utf-8", errors="replace"),
        )
    )
    db.commit()

    if event != "charge_successful" or not transaction_ref:
        return {"received": True}

    try:
        tid = UUID(str(transaction_ref))
    except (ValueError, TypeError):
        return {"received": True}

    credit_purchase = db.get(CreditPurchase, tid)
    if credit_purchase:
        if credit_purchase.status != CreditPurchaseStatus.pending:
            return {"received": True}
        try:
            squad = SquadClient()
            verify_resp = await squad.verify_transaction(transaction_ref=transaction_ref)
            status_value = (verify_resp.get("data") or {}).get("transaction_status")
            if str(status_value).lower() != "success":
                return {"received": True}
        except Exception:
            return {"received": True}

        owner = db.get(User, credit_purchase.user_id)
        if not owner:
            return {"received": True}
        owner.credits += credit_purchase.credits_granted
        credit_purchase.status = CreditPurchaseStatus.completed
        db.add(owner)
        db.add(credit_purchase)
        db.commit()
        return {"received": True}

    verification: Verification | None = db.get(Verification, tid)
    if not verification:
        return {"received": True}

    try:
        squad = SquadClient()
        verify_resp = await squad.verify_transaction(transaction_ref=transaction_ref)
        status_value = (verify_resp.get("data") or {}).get("transaction_status")
        if str(status_value).lower() != "success":
            return {"received": True}
    except Exception:
        return {"received": True}

    verification.payment_status = PaymentStatus.paid
    verification.status = VerificationStatus.processing
    db.add(verification)
    db.commit()

    background_tasks.add_task(process_verification, str(verification.id))
    return {"received": True}
