from datetime import datetime, timezone
from uuid import UUID

from django.db import transaction

from accounts.models import User
from verifications.models import Verdict, Verification, VerificationStatus
from services.groq_analyzer import analyze_document
from services.storage import read_storage_key


def _refund_credit(user_id: UUID) -> None:
    user = User.objects.select_for_update().filter(id=user_id).first()
    if user:
        user.credits += 1
        user.save(update_fields=["credits"])


def _run(verification_id: UUID) -> None:
    with transaction.atomic():
        v = Verification.objects.select_for_update().filter(id=verification_id).first()
        if not v or v.status == VerificationStatus.COMPLETE:
            return
        v.status = VerificationStatus.PROCESSING
        v.save(update_fields=["status"])

    v = Verification.objects.filter(id=verification_id).first()
    if not v:
        return

    try:
        file_bytes = read_storage_key(v.storage_key)
        result = analyze_document(filename=v.document_name, content_type=v.content_type, file_bytes=file_bytes)

        v.ai_output = result
        v.verdict = Verdict(result["verdict"])
        v.trust_score = int(result["trust_score"])
        v.summary = result["summary"]
        v.status = VerificationStatus.COMPLETE
        v.completed_at = datetime.now(timezone.utc)
    except Exception as e:
        v.status = VerificationStatus.ERROR
        v.ai_output = {"error": "AI analysis failed", "detail": str(e)}
        with transaction.atomic():
            _refund_credit(v.user_id)
    finally:
        v.save()


def process_verification(verification_id: str) -> None:
    """Runs the verification pipeline in a background thread."""
    _run(UUID(verification_id))
