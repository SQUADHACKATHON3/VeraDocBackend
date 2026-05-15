"""Rename verdict enum value SUSPICIOUS -> NEEDS REVIEW

Revision ID: 0006_verdict_needs_review
Revises: 0005_security_hardening
Create Date: 2026-05-15
"""

from alembic import op

revision = "0006_verdict_needs_review"
down_revision = "0005_security_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL requires ALTER TYPE … RENAME VALUE (Postgres 10+).
    # We first add the new value, migrate existing rows, then drop the old one
    # because Postgres does not let you remove an enum value directly.
    #
    # Strategy:
    #   1. Add new enum value 'NEEDS REVIEW' to the existing pg enum type.
    #   2. Update all rows that currently hold 'SUSPICIOUS' to 'NEEDS REVIEW'.
    #   3. The old value 'SUSPICIOUS' will simply be unused — Postgres does not
    #      support removing enum values without recreating the type, which is a
    #      heavier operation. We leave it unused; it causes no runtime issues.
    #
    # If you want a clean drop, run the commented-out block in a separate release
    # after confirming no rows carry 'SUSPICIOUS'.

    # 1. Add the new enum value.
    op.execute("ALTER TYPE verdict ADD VALUE IF NOT EXISTS 'NEEDS REVIEW'")

    # PostgreSQL requires us to commit the transaction before a newly added enum
    # value can be used in the same session.
    op.execute("COMMIT")

    # 2. Migrate existing rows.
    op.execute(
        "UPDATE verifications SET verdict = 'NEEDS REVIEW' WHERE verdict = 'SUSPICIOUS'"
    )

    # --- Optional hard cleanup (run only once 'SUSPICIOUS' rows are confirmed gone) ---
    # Recreating the type to drop 'SUSPICIOUS' requires:
    #   a) Rename old type
    #   b) Create new type without 'SUSPICIOUS'
    #   c) Alter the column to use the new type (with USING cast)
    #   d) Drop the old type
    # Uncomment and run as a follow-up migration when ready:
    #
    # op.execute("ALTER TYPE verdict RENAME TO verdict_old")
    # op.execute("CREATE TYPE verdict AS ENUM ('AUTHENTIC', 'NEEDS REVIEW', 'FAKE')")
    # op.execute(
    #     "ALTER TABLE verifications "
    #     "ALTER COLUMN verdict TYPE verdict USING verdict::text::verdict"
    # )
    # op.execute("DROP TYPE verdict_old")


def downgrade() -> None:
    # Revert rows back to 'SUSPICIOUS' (the old value still exists in the enum type).
    op.execute(
        "UPDATE verifications SET verdict = 'SUSPICIOUS' WHERE verdict = 'NEEDS REVIEW'"
    )
    # Note: We do not remove 'NEEDS REVIEW' from the enum type because PostgreSQL
    # does not support DROP VALUE on an enum without recreating the entire type.
    # The unused value is harmless.
