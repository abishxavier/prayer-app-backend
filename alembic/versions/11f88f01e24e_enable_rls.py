"""enable RLS

Revision ID: 11f88f01e24e
Revises: d2f06afc6afc
Create Date: 2026-08-12 11:40:32.772654

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '11f88f01e24e'
down_revision: Union[str, Sequence[str], None] = 'd2f06afc6afc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


tables = [
    "users",
    "refresh_tokens",
    "chats",
    "chat_members",
    "messages",
    "prayer_requests",
    "prayer_responses",
    "scheduled_calls",
]

def upgrade() -> None:
    """Upgrade schema."""
    for table in tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")

def downgrade() -> None:
    """Downgrade schema."""
    for table in tables:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
