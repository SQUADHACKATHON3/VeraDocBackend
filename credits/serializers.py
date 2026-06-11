from rest_framework import serializers


class CreditPackSerializer(serializers.Serializer):
    credits = serializers.IntegerField()
    amountKobo = serializers.IntegerField()


class CreditPacksSerializer(serializers.Serializer):
    packs = CreditPackSerializer(many=True)
    pricePerCreditKobo = serializers.IntegerField()
    currency = serializers.CharField(default="NGN")


class CreditPurchaseInitiateSerializer(serializers.Serializer):
    pack = serializers.ChoiceField(choices=[1, 5, 10, 20])


class CreditPurchaseInitiateOutSerializer(serializers.Serializer):
    purchaseId = serializers.UUIDField()
    checkoutUrl = serializers.CharField()
    credits = serializers.IntegerField()
    amountKobo = serializers.IntegerField()


class CreditPurchaseStatusSerializer(serializers.Serializer):
    purchaseId = serializers.UUIDField()
    status = serializers.CharField()
    credits = serializers.IntegerField()


class CreditPurchaseVerifySerializer(CreditPurchaseStatusSerializer):
    paymentConfirmed = serializers.BooleanField(allow_null=True, required=False)
    alreadyCompleted = serializers.BooleanField(default=False)
