import json
from uuid import UUID

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import EmailVerified
from common.background import run_in_background
from common.models import WebhookEvent
from credits.models import CreditPurchase, CreditPurchaseStatus
from verifications.models import PaymentStatus, Verification, VerificationStatus
from verifications.serializers import InitiateOutSerializer, StatusOutSerializer
from verifications.tasks import process_verification
from services.credit_purchase_completion import complete_pending_credit_purchase_by_id
from services.squad import (
    SquadClient,
    squad_payment_matches_purchase,
    squad_verify_response_indicates_success,
    verify_squad_webhook_authentic,
)
from services.storage import save_upload

ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_SIZE_BYTES = 5 * 1024 * 1024


def _normalize_declared_type(declared: str | None) -> str:
    return (declared or "application/octet-stream").split(";")[0].strip().lower()


def _effective_verification_mime(declared: str | None, filename: str | None, file_head: bytes) -> str:
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


def _record_webhook_event(*, idem_key: str, event: str, raw: bytes) -> bool:
    if WebhookEvent.objects.filter(idempotency_key=idem_key).exists():
        return False
    try:
        WebhookEvent.objects.create(
            provider="squad",
            event_type=str(event),
            idempotency_key=idem_key,
            signature_valid=True,
            raw_payload=raw.decode("utf-8", errors="replace"),
        )
        return True
    except IntegrityError:
        return False


@api_view(["POST"])
@permission_classes([IsAuthenticated, EmailVerified])
def initiate(request):
    file = request.FILES.get("file")
    if not file:
        return Response({"detail": "No file uploaded"}, status=400)

    head = file.read(8)
    file.seek(0)
    if not _upload_type_allowed(file.content_type, file.name, head):
        return Response(
            {
                "detail": (
                    "Invalid file type. Accepted: PDF, JPG, PNG "
                    "(including application/octet-stream with a matching filename or PDF magic bytes)."
                )
            },
            status=400,
        )

    storage_key, size_bytes = save_upload(file)
    if size_bytes > MAX_SIZE_BYTES:
        return Response({"detail": "File size exceeds 5MB limit"}, status=400)

    effective_mime = _effective_verification_mime(file.content_type, file.name, head)

    with transaction.atomic():
        from accounts.models import User

        u = User.objects.select_for_update().filter(id=request.user.id).first()
        if not u:
            return Response({"detail": "Unauthorized"}, status=401)
        if u.credits < 1:
            return Response(
                {
                    "detail": {
                        "message": "Insufficient credits. Buy a credit pack to run a verification.",
                        "credits": u.credits,
                    }
                },
                status=402,
            )

        u.credits -= 1
        u.save(update_fields=["credits"])

        verification = Verification.objects.create(
            user=u,
            document_name=file.name or "document",
            storage_key=storage_key,
            content_type=effective_mime,
            size_bytes=size_bytes,
            squad_transaction_ref=None,
            payment_status=PaymentStatus.PAID,
            status=VerificationStatus.PROCESSING,
        )

    run_in_background(process_verification, str(verification.id))

    return Response(
        InitiateOutSerializer(
            {"verificationId": verification.id, "creditsRemaining": u.credits}
        ).data
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def squad_webhook(request):
    raw = request.body
    enc = request.META.get("HTTP_X_SQUAD_ENCRYPTED_BODY")
    legacy = request.META.get("HTTP_X_SQUAD_SIGNATURE")
    if not verify_squad_webhook_authentic(raw, encrypted_body_header=enc, legacy_signature_header=legacy):
        return Response({"detail": "Invalid signature"}, status=401)

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return Response({"detail": "Invalid JSON"}, status=400)

    event = payload.get("Event")
    body = payload.get("Body") or {}
    transaction_ref = body.get("transaction_ref")
    if not transaction_ref:
        return Response({"received": True})

    idem_key = f"squad:{event}:{transaction_ref}"
    if not _record_webhook_event(idem_key=idem_key, event=str(event), raw=raw):
        return Response({"received": True})

    if event != "charge_successful":
        return Response({"received": True})

    try:
        tid = UUID(str(transaction_ref))
    except (ValueError, TypeError):
        return Response({"received": True})

    credit_purchase = CreditPurchase.objects.filter(id=tid).first()
    if credit_purchase:
        if credit_purchase.status != CreditPurchaseStatus.PENDING:
            return Response({"received": True})
        try:
            squad = SquadClient()
            verify_resp = squad.verify_transaction(transaction_ref=transaction_ref)
            if not squad_payment_matches_purchase(verify_resp, expected_kobo=credit_purchase.amount_kobo):
                return Response({"received": True})
        except Exception:
            return Response({"received": True})

        complete_pending_credit_purchase_by_id(tid)
        return Response({"received": True})

    verification = Verification.objects.filter(id=tid).first()
    if not verification:
        return Response({"received": True})

    if verification.status != VerificationStatus.PENDING:
        return Response({"received": True})

    try:
        squad = SquadClient()
        verify_resp = squad.verify_transaction(transaction_ref=transaction_ref)
        if not squad_verify_response_indicates_success(verify_resp):
            return Response({"received": True})
    except Exception:
        return Response({"received": True})

    verification.payment_status = PaymentStatus.PAID
    verification.status = VerificationStatus.PROCESSING
    verification.save(update_fields=["payment_status", "status"])

    run_in_background(process_verification, str(verification.id))
    return Response({"received": True})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def status_poll(request, verification_id: UUID):
    try:
        v = Verification.objects.get(id=verification_id, user=request.user)
    except Verification.DoesNotExist:
        other = Verification.objects.filter(id=verification_id).exists()
        if other:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return Response({"detail": "Verification not found"}, status=404)

    ai: dict = v.ai_output if isinstance(v.ai_output, dict) else {}
    err: str | None = None
    err_detail: str | None = None
    if v.status == VerificationStatus.ERROR:
        e = ai.get("error")
        err = str(e) if e is not None else "AI analysis failed"
        d = ai.get("detail")
        if d is not None:
            err_detail = str(d)[:4000]

    return Response(
        StatusOutSerializer(
            {
                "status": v.status,
                "verdict": v.verdict,
                "trustScore": v.trust_score,
                "summary": v.summary,
                "error": err,
                "errorDetail": err_detail,
            }
        ).data
    )
