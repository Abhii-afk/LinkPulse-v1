"""create domain blocklist and link moderation reason

Revision ID: 0004_create_domain_blocklist_and_moderation
Revises: 0003_create_click_events
Create Date: 2026-10-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_create_domain_blocklist_and_moderation"
down_revision: Union[str, Sequence[str], None] = "0003_create_click_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("links", sa.Column("deactivation_reason", sa.Text(), nullable=True))
    op.create_table(
        "domain_blocklist",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain"),
    )
    op.create_index(
        "ix_domain_blocklist_created_by",
        "domain_blocklist",
        ["created_by"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_domain_blocklist_created_by", table_name="domain_blocklist")
    op.drop_table("domain_blocklist")
    op.drop_column("links", "deactivation_reason")
