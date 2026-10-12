"""enable row-level security on PostgreSQL

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-11

"""
from collections.abc import Sequence

from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Supabase serves every table in the public schema to its anon and authenticated roles
# through the Data API. RLS with no policies denies those roles every row. The app
# connects as the tables' owner, which RLS skips unless it is FORCEd, so it is not.
# SQLite has no RLS: this revision is a no-op there.
#
# Frozen at this revision: the tables 0001 created, plus Alembic's own version table.
# A later migration that creates a table must enable RLS on it the same way;
# tests/test_row_level_security.py fails on PostgreSQL when one is missing.
TABLES = (
    'plants',
    'products',
    'regions',
    'calendar_events',
    'customers',
    'daily_sales',
    'inventory',
    'production_lines',
    'line_capabilities',
    'production_runs',
    'sales_orders',
    'sales_order_lines',
    'alembic_version',
)


def upgrade() -> None:
    if op.get_bind().dialect.name != 'postgresql':
        return
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    if op.get_bind().dialect.name != 'postgresql':
        return
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')
