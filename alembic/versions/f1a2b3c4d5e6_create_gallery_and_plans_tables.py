"""Create gallery_items and monthly_plans tables

Revision ID: f1a2b3c4d5e6
Revises: e4f5a6b7c8d9
Create Date: 2026-08-24 14:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Create gallery_items table
    bind.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS gallery_items (
            id            VARCHAR NOT NULL PRIMARY KEY,
            title         VARCHAR,
            description   TEXT,
            image_data    TEXT NOT NULL,
            uploaded_by   VARCHAR NOT NULL REFERENCES users(id),
            uploader_name VARCHAR,
            is_featured   BOOLEAN DEFAULT FALSE,
            sort_order    INTEGER DEFAULT 0,
            created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """))

    # Disable RLS on gallery_items so app user can always read and write
    try:
        bind.execute(sa.text("ALTER TABLE gallery_items DISABLE ROW LEVEL SECURITY;"))
    except Exception as e:
        print(f"[migration] Could not disable RLS on gallery_items: {e}")

    # 2. Create monthly_plans table
    bind.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS monthly_plans (
            id             VARCHAR NOT NULL PRIMARY KEY,
            title          VARCHAR NOT NULL,
            tamil_title    VARCHAR,
            category       VARCHAR NOT NULL DEFAULT 'Prayer',
            tamil_category VARCHAR,
            time           VARCHAR NOT NULL DEFAULT '06:30 PM',
            date           TIMESTAMP WITH TIME ZONE NOT NULL,
            notes          TEXT,
            tamil_notes    TEXT,
            is_recurring   BOOLEAN DEFAULT FALSE,
            completed      BOOLEAN DEFAULT FALSE,
            created_by     VARCHAR REFERENCES users(id),
            created_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """))

    # Disable RLS on monthly_plans
    try:
        bind.execute(sa.text("ALTER TABLE monthly_plans DISABLE ROW LEVEL SECURITY;"))
    except Exception as e:
        print(f"[migration] Could not disable RLS on monthly_plans: {e}")


def downgrade() -> None:
    pass
