"""operator_tasks work_log phase 16g

Revision ID: b7c2d1e9f304
Revises: a3f91c2e4b10
Create Date: 2026-06-19

Append-only operator work notes on tasks.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7c2d1e9f304"
down_revision: Union[str, Sequence[str], None] = "a3f91c2e4b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "operator_tasks",
        sa.Column(
            "work_log",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("operator_tasks", "work_log")