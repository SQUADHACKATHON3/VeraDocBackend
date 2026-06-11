from uuid import UUID

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import EmailVerified
from credits.models import CreditPurchase, CreditPurchaseStatus
from credits.serializers import (
    CreditPacksSerializer,
    CreditPackSerializer,
    CreditPurchaseInitiateOutSerializer,
    CreditPurchaseInitiateSerializer,
    CreditPurchaseStatusSerializer,
    CreditPurchaseVerifySerializer,
)
from services.credit_purchase_completion import complete_pending_credit_purchase_by_id
from services.squad import SquadClient, squad_verify_amount_kobo, squad_verify_response_indicates_success

_PACKS = (1, 5, 10, 20)


@api_view(["GET"])
@permission_classes([AllowAny])
def list_packs(request):
    unit = settings.CREDIT_PRICE_KOBO
    return Response(
        CreditPacksSerializer(
            {
                "packs": [CreditPackSerializer({"credits": p, "amountKobo": p * unit}).data for p in _PACKS],
                "pricePerCreditKobo": unit,
                "currency": settings.SQUAD_CURRENCY,
            }
        ).data
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, EmailVerified])
def initiate_credit_purchase(request):
    if not settings.SQUAD_CALLBACK_URL:
        return Response(
            {"detail": "Squad checkout is not configured: set SQUAD_CALLBACK_URL on the server."},
            status=503,
        )

    serializer = CreditPurchaseInitiateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    credits = int(serializer.validated_data["pack"])

    if credits not in _PACKS:
        return Response({"detail": "Invalid pack. Choose 1, 5, 10, or 20 credits."}, status=400)

    unit = settings.CREDIT_PRICE_KOBO
    amount_kobo = credits * unit
    user = request.user

    purchase = CreditPurchase.objects.create(
        user=user,
        credits_granted=credits,
        amount_kobo=amount_kobo,
        status=CreditPurchaseStatus.PENDING,
    )

    squad = SquadClient()
    checkout_url = squad.initiate_transaction(
        email=user.email,
        amount=amount_kobo,
        currency=settings.SQUAD_CURRENCY,
        transaction_ref=str(purchase.id),
        callback_url=settings.SQUAD_CALLBACK_URL,
    )

    return Response(
        CreditPurchaseInitiateOutSerializer(
            {
                "purchaseId": purchase.id,
                "checkoutUrl": checkout_url,
                "credits": credits,
                "amountKobo": amount_kobo,
            }
        ).data
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_credit_purchase(request, purchase_id: UUID):
    try:
        p = CreditPurchase.objects.get(id=purchase_id, user=request.user)
    except CreditPurchase.DoesNotExist:
        return Response({"detail": "Purchase not found"}, status=status.HTTP_404_NOT_FOUND)

    if p.status == CreditPurchaseStatus.COMPLETED:
        return Response(
            CreditPurchaseVerifySerializer(
                {
                    "purchaseId": p.id,
                    "status": p.status,
                    "credits": p.credits_granted,
                    "alreadyCompleted": True,
                    "paymentConfirmed": True,
                }
            ).data
        )

    if p.status == CreditPurchaseStatus.FAILED:
        return Response({"detail": "This purchase failed; start a new checkout."}, status=400)

    try:
        squad = SquadClient()
        verify_resp = squad.verify_transaction(transaction_ref=str(purchase_id))
    except Exception:
        return Response({"detail": "Squad verify request failed"}, status=502)

    if not squad_verify_response_indicates_success(verify_resp):
        return Response(
            CreditPurchaseVerifySerializer(
                {
                    "purchaseId": p.id,
                    "status": p.status,
                    "credits": p.credits_granted,
                    "paymentConfirmed": False,
                    "alreadyCompleted": False,
                }
            ).data
        )

    paid = squad_verify_amount_kobo(verify_resp)
    if paid is not None and paid != p.amount_kobo:
        return Response(
            CreditPurchaseVerifySerializer(
                {
                    "purchaseId": p.id,
                    "status": p.status,
                    "credits": p.credits_granted,
                    "paymentConfirmed": False,
                    "alreadyCompleted": False,
                }
            ).data
        )

    p_final = complete_pending_credit_purchase_by_id(purchase_id)
    if not p_final:
        return Response({"detail": "Purchase not found"}, status=status.HTTP_404_NOT_FOUND)

    return Response(
        CreditPurchaseVerifySerializer(
            {
                "purchaseId": p_final.id,
                "status": p_final.status,
                "credits": p_final.credits_granted,
                "paymentConfirmed": p_final.status == CreditPurchaseStatus.COMPLETED,
                "alreadyCompleted": False,
            }
        ).data
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def purchase_status(request, purchase_id: UUID):
    try:
        p = CreditPurchase.objects.get(id=purchase_id, user=request.user)
    except CreditPurchase.DoesNotExist:
        return Response({"detail": "Purchase not found"}, status=status.HTTP_404_NOT_FOUND)

    return Response(
        CreditPurchaseStatusSerializer(
            {"purchaseId": p.id, "status": p.status, "credits": p.credits_granted}
        ).data
    )
