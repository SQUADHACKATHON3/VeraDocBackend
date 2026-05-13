from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.verification import Verdict, Verification, VerificationStatus
from app.services.groq_analyzer import analyze_document
from app.services.storage import read_storage_key
from app.tasks.celery_app import celery_app


def _run(db: Session, verification_id: UUID) -> None:
    v = db.get(Verification, verification_id)
    if not v:
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
    finally:
        db.add(v)
        db.commit()


@celery_app.task(name="veradoc.run_verification")
def run_verification(verification_id: str) -> None:
    db = SessionLocal()
    try:
        _run(db, UUID(verification_id))
    finally:
        db.close()

