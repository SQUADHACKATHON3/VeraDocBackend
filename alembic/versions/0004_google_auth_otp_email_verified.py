"""google auth, otp_codes table, email_verified, google_id on users

Revision ID: 0004_google_auth_otp
Revises: 0003_signup_free_credits
Create Date: 2026-05-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_google_auth_otp"
down_revision = "0003_signup_free_credits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users: new columns ────────────────────────────────────────────────────
    op.add_column("users", sa.Column("google_id", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.alter_column("users", "password_hash", nullable=True)
    op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)

    # ── otp_codes table ───────────────────────────────────────────────────────
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE otptype AS ENUM ('email_verification', 'password_reset');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    otp_type_col = postgresql.ENUM(
        "email_verification", "password_reset", name="otptype", create_type=False
    )
    op.create_table(
        "otp_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("otp_type", otp_type_col, nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_otp_codes_user_id", "otp_codes", ["user_id"])
    op.create_index("ix_otp_codes_email", "otp_codes", ["email"])


def downgrade() -> None:
    op.drop_index("ix_otp_codes_email", table_name="otp_codes")
    op.drop_index("ix_otp_codes_user_id", table_name="otp_codes")
    op.drop_table("otp_codes")
    op.execute("DROP TYPE IF EXISTS otptype")

    op.drop_index("ix_users_google_id", table_name="users")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "google_id")
    op.alter_column("users", "password_hash", nullable=False)
