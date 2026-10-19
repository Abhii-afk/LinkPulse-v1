"""create campaigns and links tables

Revision ID: 0002_create_campaigns_and_links
Revises: 0001_create_users
Create Date: 2026-10-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_create_campaigns_and_links"
down_revision: Union[str, Sequence[str], None] = "0001_create_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaigns_user_id", "campaigns", ["user_id"], unique=False)

    op.create_table(
        "links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("short_code", sa.String(length=100), nullable=False),
        sa.Column("destination_url", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("click_limit", sa.Integer(), nullable=True),
        sa.Column("total_clicks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_abusive", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "click_limit IS NULL OR click_limit > 0",
            name="ck_links_click_limit_positive",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("short_code"),
    )
    op.create_index("ix_links_user_id", "links", ["user_id"], unique=False)
    op.create_index("ix_links_campaign_id", "links", ["campaign_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_links_campaign_id", table_name="links")
    op.drop_index("ix_links_user_id", table_name="links")
    op.drop_table("links")
    op.drop_index("ix_campaigns_user_id", table_name="campaigns")
    op.drop_table("campaigns")
