"""create click events table

Revision ID: 0003_create_click_events
Revises: 0002_create_campaigns_and_links
Create Date: 2026-10-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_create_click_events"
down_revision: Union[str, Sequence[str], None] = "0002_create_campaigns_and_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "click_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("link_id", sa.Uuid(), nullable=False),
        sa.Column("stream_message_id", sa.String(length=64), nullable=False),
        sa.Column(
            "clicked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("country_code", sa.String(length=10), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("browser", sa.String(length=100), nullable=True),
        sa.Column("os", sa.String(length=100), nullable=True),
        sa.Column("device_type", sa.String(length=50), nullable=True),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("is_bot", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_anomalous", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stream_message_id", name="uq_click_events_stream_message_id"),
    )
    op.create_index("ix_click_events_link_id", "click_events", ["link_id"], unique=False)
    op.create_index("ix_click_events_clicked_at", "click_events", ["clicked_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_click_events_clicked_at", table_name="click_events")
    op.drop_index("ix_click_events_link_id", table_name="click_events")
    op.drop_table("click_events")
