"""add device columns to refresh_tokens

Revision ID: c9a2f9d4e1b3
Revises: b4f2e3c9a7d4
Create Date: 2026-08-07 19:27:30.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9a2f9d4e1b3'
down_revision: Union[str, Sequence[str], None] = 'b4f2e3c9a7d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('refresh_tokens', sa.Column('device_id', sa.String(), nullable=True))
    op.add_column('refresh_tokens', sa.Column('device_info', sa.String(), nullable=True))
    op.create_index(op.f('ix_refresh_tokens_device_id'), 'refresh_tokens', ['device_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_refresh_tokens_device_id'), table_name='refresh_tokens')
    op.drop_column('refresh_tokens', 'device_info')
    op.drop_column('refresh_tokens', 'device_id')
