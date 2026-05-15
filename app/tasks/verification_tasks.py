from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.models.verification import Verdict, Verification, VerificationStatus
from app.services.groq_analyzer import analyze_document
from app.services.storage import read_storage_key


def _refund_credit(db: Session, user_id: UUID) -> None:
    u = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if u:
        u.credits += 1
        db.add(u)


def _run(db: Session, verification_id: UUID) -> None:
    v = db.get(Verification, verification_id)
    if not v:
        return

    if v.status == VerificationStatus.complete:
        return

    v.status = VerificationStatus.processing
    db.add(v)
    db.commit()

    try:
        file_bytes = read_storage_key(v.storage_key)
        result = analyze_document(filename=v.document_name, content_type=v.content_type, file_bytes=file_bytes)

        v.ai_output = result
        v.verdict = Verdict(result["verdict"])
        v.trust_score = int(result["trust_score"])
        v.summary = result["summary"]
        v.status = VerificationStatus.complete
        v.completed_at = datetime.now(timezone.utc)
    except Exception as e:
        v.status = VerificationStatus.error
        v.ai_output = {"error": "AI analysis failed", "detail": str(e)}
        _refund_credit(db, v.user_id)
    finally:
        db.add(v)
        db.commit()


def process_verification(verification_id: str) -> None:
    """
    Runs the verification pipeline in a worker thread (via FastAPI BackgroundTasks).
    Same DB/session pattern as before; no Celery or Redis required.
    """
    db = SessionLocal()
    try:
        _run(db, UUID(verification_id))
    finally:
        db.close()
