import uuid

from django.db import models


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "pending"
    PAID = "paid", "paid"
    FAILED = "failed", "failed"


class VerificationStatus(models.TextChoices):
    PENDING = "pending", "pending"
    PROCESSING = "processing", "processing"
    COMPLETE = "complete", "complete"
    ERROR = "error", "error"


class Verdict(models.TextChoices):
    AUTHENTIC = "AUTHENTIC", "AUTHENTIC"
    NEEDS_REVIEW = "NEEDS REVIEW", "NEEDS REVIEW"
    FAKE = "FAKE", "FAKE"


class Verification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="verifications",
        db_column="user_id",
        db_index=True,
    )
    document_name = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=512)
    content_type = models.CharField(max_length=100)
    size_bytes = models.IntegerField()
    squad_transaction_ref = models.CharField(max_length=128, null=True, blank=True, db_index=True)
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )
    verdict = models.CharField(max_length=20, choices=Verdict.choices, null=True, blank=True)
    trust_score = models.IntegerField(null=True, blank=True)
    summary = models.CharField(max_length=500, null=True, blank=True)
    ai_output = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "verifications"
