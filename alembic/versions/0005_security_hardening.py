"""otp failed_attempts, unique webhook idempotency

Revision ID: 0005_security_hardening
Revises: 0004_google_auth_otp
Create Date: 2026-05-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_security_hardening"
down_revision = "0004_google_auth_otp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "otp_codes",
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_unique_constraint("uq_otp_codes_email_type", "otp_codes", ["email", "otp_type"])
    op.create_unique_constraint(
        "uq_webhook_events_idempotency_key", "webhook_events", ["idempotency_key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_webhook_events_idempotency_key", "webhook_events", type_="unique")
    op.drop_constraint("uq_otp_codes_email_type", "otp_codes", type_="unique")
    op.drop_column("otp_codes", "failed_attempts")
