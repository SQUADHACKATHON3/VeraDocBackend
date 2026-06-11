import uuid

from django.db import models


class OtpType(models.TextChoices):
    EMAIL_VERIFICATION = "email_verification", "email_verification"
    PASSWORD_RESET = "password_reset", "password_reset"


class OtpCode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="otp_codes",
        db_column="user_id",
    )
    email = models.EmailField(max_length=320, db_index=True)
    otp_type = models.CharField(max_length=32, choices=OtpType.choices)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    failed_attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "otp_codes"
        constraints = [
            models.UniqueConstraint(fields=["email", "otp_type"], name="uq_otp_codes_email_type"),
        ]


class WebhookEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=50)
    event_type = models.CharField(max_length=100)
    idempotency_key = models.CharField(max_length=150, unique=True, db_index=True)
    signature_valid = models.BooleanField(default=False)
    raw_payload = models.TextField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "webhook_events"
