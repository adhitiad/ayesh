"""monologues table for per-user internal monologue

Revision ID: ad80037e2aa2
Revises: 721880c620d6
Create Date: 2026-09-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad80037e2aa2'
down_revision: Union[str, Sequence[str], None] = '721880c620d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('monologues',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=100), nullable=False),
    sa.Column('agent_type', sa.String(length=50), nullable=False),
    sa.Column('role', sa.String(length=50), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_monologues_user_id'), 'monologues', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_monologues_user_id'), table_name='monologues')
    op.drop_table('monologues')
