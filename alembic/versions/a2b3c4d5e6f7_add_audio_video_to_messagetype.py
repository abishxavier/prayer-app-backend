"""add audio and video to messagetype enum

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-08-25 12:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    try:
        bind.execute(sa.text("ALTER TYPE messagetype ADD VALUE IF NOT EXISTS 'audio'"))
        bind.execute(sa.text("ALTER TYPE messagetype ADD VALUE IF NOT EXISTS 'video'"))
    except Exception:
        pass


def downgrade() -> None:
    pass
