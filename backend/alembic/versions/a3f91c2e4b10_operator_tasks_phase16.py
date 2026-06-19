"""operator_tasks phase 16

Revision ID: a3f91c2e4b10
Revises: 17826c8d15fa
Create Date: 2026-06-19

EA lane — FAB admin tasks in PostgreSQL execution truth.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3f91c2e4b10"
down_revision: Union[str, Sequence[str], None] = "17826c8d15fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operator_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("raw_dump", sa.Text(), nullable=False),
        sa.Column("task_kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.String(length=64), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_label", sa.String(length=256), nullable=True),
        sa.Column("context_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("attendees", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("location", sa.String(length=512), nullable=True),
        sa.Column("waiting_on", sa.String(length=256), nullable=True),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("checklist", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("llm_polish", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operator_tasks_status", "operator_tasks", ["status"])
    op.create_index("ix_operator_tasks_due_at", "operator_tasks", ["due_at"])


def downgrade() -> None:
    op.drop_index("ix_operator_tasks_due_at", table_name="operator_tasks")
    op.drop_index("ix_operator_tasks_status", table_name="operator_tasks")
    op.drop_table("operator_tasks")