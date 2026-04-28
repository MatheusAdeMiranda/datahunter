"""create scraped_books table

Revision ID: 0001
Revises:
Create Date: 2026-04-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.create_table(
        "scraped_books",
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("price", sa.String(), nullable=False),
        sa.Column("availability", sa.String(), nullable=False),
        sa.Column("rating", sa.String(), nullable=False),
        sa.Column("scraped_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("title"),
    )


def downgrade() -> None:
    op.drop_table("scraped_books")
