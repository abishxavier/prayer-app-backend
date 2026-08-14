"""Fix scheduled_calls RLS visibility and add testimonies table

This migration addresses two issues:
1. The scheduled_calls table had RLS enabled (from 11f88f01e24e) but no
   permissive policy was ever created, so the backend app user could not
   read rows created by other users. This caused GET /calls/scheduled to
   return 0 rows for all users silently.
2. The testimonies table was created only via Base.metadata.create_all()
   at startup, but was not tracked by Alembic. This migration creates it
   properly so it is managed by migrations going forward.

Revision ID: a1b2c3d4e5f6
Revises: 91bf02618a78
Create Date: 2026-08-15 00:13:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '91bf02618a78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix RLS on scheduled_calls and create testimonies table."""
    bind = op.get_bind()

    # ── 1. Disable RLS on scheduled_calls so the backend postgres user ──
    #        can always SELECT all rows regardless of who created them.
    #        The original 11f88f01e24e migration enabled RLS but never
    #        added a permissive policy, causing reads to silently return 0.
    try:
        bind.execute(sa.text("ALTER TABLE scheduled_calls DISABLE ROW LEVEL SECURITY;"))
    except Exception as e:
        print(f"[migration] Could not disable RLS on scheduled_calls (may already be off): {e}")

    # ── 2. Also drop any leftover RLS policies on scheduled_calls ──
    try:
        bind.execute(sa.text(
            "DROP POLICY IF EXISTS scheduled_calls_policy ON scheduled_calls;"
        ))
    except Exception as e:
        print(f"[migration] No policy to drop on scheduled_calls: {e}")

    # ── 3. Create testimonies table if it does not already exist ──
    #       (create_all may have already created it; use IF NOT EXISTS to be safe)
    bind.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS testimonies (
            id          VARCHAR NOT NULL,
            user_id     VARCHAR NOT NULL REFERENCES users(id),
            user_name   VARCHAR,
            user_image  TEXT,
            title       VARCHAR NOT NULL,
            content     TEXT NOT NULL,
            likes       INTEGER DEFAULT 0,
            shares      INTEGER DEFAULT 0,
            created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            PRIMARY KEY (id)
        );
    """))

    # ── 4. Disable RLS on testimonies so all users can read all testimonies ──
    try:
        bind.execute(sa.text("ALTER TABLE testimonies DISABLE ROW LEVEL SECURITY;"))
    except Exception as e:
        print(f"[migration] Could not disable RLS on testimonies: {e}")


def downgrade() -> None:
    """Re-enable RLS on scheduled_calls (restores previous broken state for rollback)."""
    bind = op.get_bind()
    try:
        bind.execute(sa.text("ALTER TABLE scheduled_calls ENABLE ROW LEVEL SECURITY;"))
    except Exception:
        pass
    # Do NOT drop testimonies on downgrade — data loss risk
