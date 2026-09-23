"""plans and plan_steps tables for multi-step planning

Revision ID: 7f3a9c21d4b8
Revises: ad80037e2aa2
Create Date: 2026-09-22

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f3a9c21d4b8"
down_revision: str | Sequence[str] | None = "ad80037e2aa2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=100), nullable=True),
        sa.Column("judul", sa.String(length=200), nullable=False),
        sa.Column("tujuan", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("langkah_selesai", sa.Integer(), nullable=False),
        sa.Column("total_langkah", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plans_owner_user_id"), "plans", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_plans_session_id"), "plans", ["session_id"], unique=False)
    op.create_index(op.f("ix_plans_status"), "plans", ["status"], unique=False)
    op.create_table(
        "plan_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("urutan", sa.Integer(), nullable=False),
        sa.Column("deskripsi", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("hasil", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plan_steps_plan_id"), "plan_steps", ["plan_id"], unique=False)
    op.create_index(op.f("ix_plan_steps_status"), "plan_steps", ["status"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_plan_steps_status"), table_name="plan_steps")
    op.drop_index(op.f("ix_plan_steps_plan_id"), table_name="plan_steps")
    op.drop_table("plan_steps")
    op.drop_index(op.f("ix_plans_status"), table_name="plans")
    op.drop_index(op.f("ix_plans_session_id"), table_name="plans")
    op.drop_index(op.f("ix_plans_owner_user_id"), table_name="plans")
    op.drop_table("plans")
