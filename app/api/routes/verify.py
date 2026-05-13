import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.credit_purchase import CreditPurchase, CreditPurchaseStatus
from app.models.user import User
from app.models.verification import PaymentStatus, Verification, VerificationStatus
from app.models.webhook_event import WebhookEvent
from app.schemas.verification import InitiateOut, StatusOut
from app.services.squad import SquadClient, verify_squad_signature
from app.services.storage import save_upload_locally
from app.tasks.verification_tasks import run_verification

router = APIRouter(prefix="/api/verify", tags=["verify"])

ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_SIZE_BYTES = 5 * 1024 * 1024


@router.post("/initiate", response_model=InitiateOut)
async def initiate(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InitiateOut:
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Invalid file type. Accepted: PDF, JPG, PNG, JPEG")

    storage_key, size_bytes = save_upload_locally(file)
    if size_bytes > MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File size exceeds 5MB limit")

    u = db.execute(select(User).where(User.id == user.id).with_for_update()).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if u.credits < 1:
        raise HTTPException(
            status_code=402,
            detail={
                "message": "Insufficient credits. Buy a credit pack to run a verification.",
                "credits": u.credits,
            },
        )

    u.credits -= 1

    verification = Verification(
        user_id=user.id,
        document_name=file.filename or "document",
        storage_key=storage_key,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=size_bytes,
        squad_transaction_ref=None,
        payment_status=PaymentStatus.paid,
        status=VerificationStatus.processing,
    )
    db.add(verification)
    db.commit()
    db.refresh(verification)

    run_verification.delay(str(verification.id))

    return InitiateOut(verificationId=verification.id, creditsRemaining=u.credits)


@router.post("/webhook")
async def squad_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
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

    run_verification.delay(str(verification.id))
    return {"received": True}


@router.get("/{verification_id}/status", response_model=StatusOut)
def status_poll(
    verification_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StatusOut:
    v: Verification | None = db.get(Verification, verification_id)
    if not v:
        raise HTTPException(status_code=404, detail="Verification not found")
    if v.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return StatusOut(
        status=v.status.value,
        verdict=v.verdict.value if v.verdict else None,
        trustScore=v.trust_score,
        summary=v.summary,
    )
