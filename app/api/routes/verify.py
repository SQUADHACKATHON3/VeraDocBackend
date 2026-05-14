from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.squad_webhook_handler import handle_squad_charge_webhook
from app.models.user import User
from app.models.verification import PaymentStatus, Verification, VerificationStatus
from app.schemas.verification import InitiateOut, StatusOut
from app.services.storage import save_upload
from app.tasks.verification_tasks import process_verification

router = APIRouter(prefix="/api/verify", tags=["verify"])

ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_SIZE_BYTES = 5 * 1024 * 1024


def _normalize_declared_type(declared: str | None) -> str:
    return (declared or "application/octet-stream").split(";")[0].strip().lower()


def _effective_verification_mime(declared: str | None, filename: str | None, file_head: bytes) -> str:
    """Resolve browser quirks so the pipeline gets application/pdf or image/*."""
    if len(file_head) >= 4 and file_head[:4] == b"%PDF":
        return "application/pdf"
    base = _normalize_declared_type(declared)
    name = (filename or "").lower()
    if base == "application/pdf" or name.endswith(".pdf"):
        return "application/pdf"
    if base in ("image/jpeg", "image/jpg") or name.endswith((".jpg", ".jpeg", ".jpe")):
        return "image/jpeg"
    if base == "image/png" or name.endswith(".png"):
        return "image/png"
    if base == "application/octet-stream":
        if name.endswith(".pdf"):
            return "application/pdf"
        if name.endswith((".jpg", ".jpeg", ".jpe")):
            return "image/jpeg"
        if name.endswith(".png"):
            return "image/png"
    return base


def _upload_type_allowed(declared: str | None, filename: str | None, file_head: bytes) -> bool:
    return _effective_verification_mime(declared, filename, file_head) in ALLOWED_TYPES


@router.post("/initiate", response_model=InitiateOut)
async def initiate(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InitiateOut:
    head = await file.read(8)
    await file.seek(0)
    if not _upload_type_allowed(file.content_type, file.filename, head):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Accepted: PDF, JPG, PNG (including application/octet-stream with a matching filename or PDF magic bytes).",
        )

    storage_key, size_bytes = save_upload(file)
    if size_bytes > MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File size exceeds 5MB limit")

    effective_mime = _effective_verification_mime(file.content_type, file.filename, head)
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
        content_type=effective_mime,
        size_bytes=size_bytes,
        squad_transaction_ref=None,
        payment_status=PaymentStatus.paid,
        status=VerificationStatus.processing,
    )
    db.add(verification)
    db.commit()
    db.refresh(verification)

    background_tasks.add_task(process_verification, str(verification.id))

    return InitiateOut(verificationId=verification.id, creditsRemaining=u.credits)


@router.post("/webhook")
async def squad_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    return await handle_squad_charge_webhook(request, background_tasks, db)


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
