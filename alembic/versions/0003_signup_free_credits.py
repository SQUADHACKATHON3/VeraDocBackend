"""signup free credits default 3

Revision ID: 0003_signup_free_credits
Revises: 0002_user_credits
Create Date: 2026-05-14
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_signup_free_credits"
down_revision = "0002_user_credits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "credits",
        existing_type=sa.Integer(),
        server_default="3",
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "credits",
        existing_type=sa.Integer(),
        server_default="1",
    )
