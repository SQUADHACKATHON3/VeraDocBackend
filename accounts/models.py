import uuid

from django.db import models


class User(models.Model):
    """Maps to the existing `users` table (formerly SQLAlchemy)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    organisation = models.CharField(max_length=200)
    email = models.EmailField(max_length=320, unique=True, db_index=True)
    password_hash = models.CharField(max_length=255, null=True, blank=True)
    google_id = models.CharField(max_length=255, null=True, blank=True, unique=True, db_index=True)
    email_verified = models.BooleanField(default=False)
    credits = models.IntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "users"

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    def __str__(self) -> str:
        return self.email

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    @property
    def is_staff(self) -> bool:
        return False

    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_superuser(self) -> bool:
        return False

    def get_full_name(self) -> str:
        return self.name

    def get_short_name(self) -> str:
        return self.name
