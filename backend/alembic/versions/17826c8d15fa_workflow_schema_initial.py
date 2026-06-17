"""workflow schema initial

Revision ID: 17826c8d15fa
Revises:
Create Date: 2026-06-17 14:02:22.225056

Workflow tables only. Intel tables (intel_*) are owned by scripts/run-intel-migration.ps1.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "17826c8d15fa"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("slug", sa.String(length=512), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=64), nullable=False),
        sa.Column("current_milestone_gate", sa.String(length=64), nullable=False),
        sa.Column("capture_phase_band", sa.String(length=64), nullable=False),
        sa.Column("urgency_score", sa.Float(), nullable=False),
        sa.Column("freshness_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_reason", sa.String(length=128), nullable=False),
        sa.Column("intel_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "packet_field_definitions",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=256), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("section", sa.String(length=128), nullable=False),
        sa.Column("value_kind", sa.String(length=64), nullable=False),
        sa.Column("required_gates", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("route_kind", sa.String(length=64), nullable=False),
        sa.Column("reference_slide", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "packet_field_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("trust_level", sa.String(length=64), nullable=False),
        sa.Column("review_state", sa.String(length=64), nullable=True),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "action_matrix_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(length=256), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("linked_field_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "review_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("entity_id", sa.String(length=256), nullable=False),
        sa.Column("trust_level", sa.String(length=64), nullable=False),
        sa.Column("review_state", sa.String(length=64), nullable=False),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "capability_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("transcript", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("capability_runs")
    op.drop_table("review_records")
    op.drop_table("action_matrix_items")
    op.drop_table("packet_field_answers")
    op.drop_table("packet_field_definitions")
    op.drop_table("opportunities")