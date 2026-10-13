"""Add invited_user_ids to scheduled_calls

Revision ID: a3b4c5d6e7f8
Revises: 57c6866dcca5
Create Date: 2026-10-13 21:38:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, Sequence[str], None] = '47a11271990d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add invited_user_ids column for selective call ring feature."""
    op.add_column(
        'scheduled_calls',
        sa.Column('invited_user_ids', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove invited_user_ids column."""
    op.drop_column('scheduled_calls', 'invited_user_ids')
