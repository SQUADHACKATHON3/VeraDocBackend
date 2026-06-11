import uuid

from django.db import models


class CreditPurchaseStatus(models.TextChoices):
    PENDING = "pending", "pending"
    COMPLETED = "completed", "completed"
    FAILED = "failed", "failed"


class CreditPurchase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="credit_purchases",
        db_column="user_id",
        db_index=True,
    )
    credits_granted = models.IntegerField()
    amount_kobo = models.IntegerField()
    status = models.CharField(
        max_length=20,
        choices=CreditPurchaseStatus.choices,
        default=CreditPurchaseStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "credit_purchases"
