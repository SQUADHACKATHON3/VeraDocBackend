"""Shared Squad payment webhook logic (credit purchases + legacy per-verification pay)."""

import json
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.credit_purchase import CreditPurchase, CreditPurchaseStatus
from app.models.verification import PaymentStatus, Verification, VerificationStatus
from app.models.webhook_event import WebhookEvent
from app.services.credit_purchase_completion import complete_pending_credit_purchase_by_id
from app.services.squad import (
    SquadClient,
    squad_payment_matches_purchase,
    squad_verify_response_indicates_success,
    verify_squad_webhook_authentic,
)
from app.tasks.verification_tasks import process_verification


def _record_webhook_event(db: Session, *, idem_key: str, event: str, raw: bytes) -> bool:
    """Insert idempotency row. Returns False if this delivery was already processed."""
    existing = db.scalar(select(WebhookEvent).where(WebhookEvent.idempotency_key == idem_key))
    if existing:
        return False
    db.add(
        WebhookEvent(
            provider="squad",
            event_type=str(event),
            idempotency_key=idem_key,
            signature_valid=True,
            raw_payload=raw.decode("utf-8", errors="replace"),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    return True


async def handle_squad_charge_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session,
) -> dict:
    raw = await request.body()
    enc = request.headers.get("x-squad-encrypted-body")
    legacy = request.headers.get("x-squad-signature")
    sig_valid = verify_squad_webhook_authentic(
        raw,
        encrypted_body_header=enc,
        legacy_signature_header=legacy,
    )
    if not sig_valid:
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = payload.get("Event")
    body = payload.get("Body") or {}
    transaction_ref = body.get("transaction_ref")
    if not transaction_ref:
        return {"received": True}

    idem_key = f"squad:{event}:{transaction_ref}"
    if not _record_webhook_event(db, idem_key=idem_key, event=str(event), raw=raw):
        return {"received": True}

    if event != "charge_successful":
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
            if not squad_payment_matches_purchase(verify_resp, expected_kobo=credit_purchase.amount_kobo):
                return {"received": True}
        except Exception:
            return {"received": True}

        complete_pending_credit_purchase_by_id(db, tid)
        return {"received": True}

    verification: Verification | None = db.get(Verification, tid)
    if not verification:
        return {"received": True}

    if verification.status not in (VerificationStatus.pending,):
        return {"received": True}

    try:
        squad = SquadClient()
        verify_resp = await squad.verify_transaction(transaction_ref=transaction_ref)
        if not squad_verify_response_indicates_success(verify_resp):
            return {"received": True}
    except Exception:
        return {"received": True}

    verification.payment_status = PaymentStatus.paid
    verification.status = VerificationStatus.processing
    db.add(verification)
    db.commit()

    background_tasks.add_task(process_verification, str(verification.id))
    return {"received": True}
