"""Add image_url to testimonies table

Revision ID: e4f5a6b7c8d9
Revises: a1b2c3d4e5f6
Create Date: 2026-08-19 17:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    try:
        bind.execute(sa.text("ALTER TABLE testimonies ADD COLUMN IF NOT EXISTS image_url TEXT;"))
    except Exception as e:
        print(f"[migration] Could not add image_url to testimonies (may already exist): {e}")


def downgrade() -> None:
    bind = op.get_bind()
    try:
        bind.execute(sa.text("ALTER TABLE testimonies DROP COLUMN IF EXISTS image_url;"))
    except Exception:
        pass
