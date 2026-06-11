from uuid import UUID

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from verifications.models import Verdict, Verification
from verifications.serializers import (
    VerificationDetailSerializer,
    VerificationListItemSerializer,
    VerificationListSerializer,
    issuer_contact_hints_from_ai,
)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_verifications(request):
    page = max(1, int(request.query_params.get("page", 1)))
    limit = min(100, max(1, int(request.query_params.get("limit", 10))))
    verdict = request.query_params.get("verdict")
    search = request.query_params.get("search")

    qs = Verification.objects.filter(user=request.user)

    if verdict:
        try:
            Verdict(verdict)
        except ValueError:
            return Response({"detail": "Invalid verdict filter"}, status=400)
        qs = qs.filter(verdict=verdict)

    if search:
        qs = qs.filter(document_name__icontains=search)

    total = qs.count()
    items = qs.order_by("-created_at")[(page - 1) * limit : page * limit]

    return Response(
        VerificationListSerializer(
            {
                "data": [
                    VerificationListItemSerializer(
                        {
                            "id": v.id,
                            "documentName": v.document_name,
                            "verdict": v.verdict,
                            "trustScore": v.trust_score,
                            "status": v.status,
                            "createdAt": v.created_at,
                        }
                    ).data
                    for v in items
                ],
                "total": total,
                "page": page,
                "limit": limit,
            }
        ).data
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_verification(request, verification_id: UUID):
    try:
        v = Verification.objects.get(id=verification_id, user=request.user)
    except Verification.DoesNotExist:
        other = Verification.objects.filter(id=verification_id).exists()
        if other:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return Response({"detail": "Verification not found"}, status=status.HTTP_404_NOT_FOUND)

    ai = v.ai_output or {}
    flags = ai.get("flags")
    passed_checks = ai.get("passed_checks")

    return Response(
        VerificationDetailSerializer(
            {
                "id": v.id,
                "documentName": v.document_name,
                "squadTransactionRef": v.squad_transaction_ref,
                "paymentStatus": v.payment_status,
                "status": v.status,
                "verdict": v.verdict,
                "trustScore": v.trust_score,
                "flags": flags if isinstance(flags, list) else None,
                "passedChecks": passed_checks if isinstance(passed_checks, list) else None,
                "summary": v.summary,
                "issuerContactHints": issuer_contact_hints_from_ai(ai, document_filename=v.document_name),
                "createdAt": v.created_at,
                "completedAt": v.completed_at,
            }
        ).data
    )
