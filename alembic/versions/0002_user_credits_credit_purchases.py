"""user credits and credit_purchases

Revision ID: 0002_user_credits
Revises: 0001_init
Create Date: 2026-05-13
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_user_credits"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("credits", sa.Integer(), nullable=False, server_default="1"))
    op.execute("UPDATE users SET credits = 1 WHERE credits IS NULL")

    # Create PG enum once. Do not rely on sa.Enum.create + create_table (that emits CREATE TYPE twice).
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE creditpurchasestatus AS ENUM ('pending', 'completed', 'failed');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    status_t = postgresql.ENUM(
        "pending",
        "completed",
        "failed",
        name="creditpurchasestatus",
        create_type=False,
    )

    op.create_table(
        "credit_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("credits_granted", sa.Integer(), nullable=False),
        sa.Column("amount_kobo", sa.Integer(), nullable=False),
        sa.Column("status", status_t, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_credit_purchases_user_id", "credit_purchases", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_credit_purchases_user_id", table_name="credit_purchases")
    op.drop_table("credit_purchases")
    op.execute("DROP TYPE IF EXISTS creditpurchasestatus")
    op.drop_column("users", "credits")
