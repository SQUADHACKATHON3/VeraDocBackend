"""init

Revision ID: 0001_init
Revises: 
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("organisation", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    op.create_table(
        "verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("document_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("squad_transaction_ref", sa.String(length=128), nullable=True),
        sa.Column("payment_status", sa.Enum("pending", "paid", "failed", name="paymentstatus"), nullable=False),
        sa.Column("status", sa.Enum("pending", "processing", "complete", "error", name="verificationstatus"), nullable=False),
        sa.Column("verdict", sa.Enum("AUTHENTIC", "SUSPICIOUS", "FAKE", name="verdict"), nullable=True),
        sa.Column("trust_score", sa.Integer(), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=True),
        sa.Column("ai_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_verifications_user_id", "verifications", ["user_id"])
    op.create_index("ix_verifications_squad_transaction_ref", "verifications", ["squad_transaction_ref"])

    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=150), nullable=False),
        sa.Column("signature_valid", sa.Boolean(), nullable=False),
        sa.Column("raw_payload", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_webhook_events_idempotency_key", "webhook_events", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_webhook_events_idempotency_key", table_name="webhook_events")
    op.drop_table("webhook_events")

    op.drop_index("ix_verifications_squad_transaction_ref", table_name="verifications")
    op.drop_index("ix_verifications_user_id", table_name="verifications")
    op.drop_table("verifications")
    op.execute("DROP TYPE IF EXISTS verdict")
    op.execute("DROP TYPE IF EXISTS verificationstatus")
    op.execute("DROP TYPE IF EXISTS paymentstatus")

    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

