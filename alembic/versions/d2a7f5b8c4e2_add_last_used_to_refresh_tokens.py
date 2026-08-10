"""add last_used_at to refresh_tokens

Revision ID: d2a7f5b8c4e2
Revises: c9a2f9d4e1b3
Create Date: 2026-08-07 19:33:40.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2a7f5b8c4e2'
down_revision: Union[str, Sequence[str], None] = 'c9a2f9d4e1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('refresh_tokens', sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_refresh_tokens_last_used_at'), 'refresh_tokens', ['last_used_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_refresh_tokens_last_used_at'), table_name='refresh_tokens')
    op.drop_column('refresh_tokens', 'last_used_at')
