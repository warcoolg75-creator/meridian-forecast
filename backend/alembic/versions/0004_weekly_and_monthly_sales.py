"""weekly and monthly rollups of daily_sales

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-20

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Row-level security on every new table, as 0002 does for the original ones.
TABLES = ('weekly_sales', 'monthly_sales')

CHANNELS = ('distributor', 'retail', 'ecommerce', 'direct', 'export')


def _create(table: str) -> None:
    # The channel Enum has create_constraint=False and its CHECK is listed once, as in 0001.
    op.create_table(table,
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('region_id', sa.Integer(), nullable=False),
    sa.Column('channel', sa.Enum(*CHANNELS, name='channel', native_enum=False, create_constraint=False, length=20), nullable=False),
    sa.Column('units', sa.Integer(), nullable=False),
    sa.Column('revenue_minor', sa.BigInteger(), nullable=False),
    sa.Column('order_count', sa.Integer(), nullable=True),
    sa.CheckConstraint("channel IN ('distributor', 'retail', 'ecommerce', 'direct', 'export')", name=op.f(f'ck_{table}_channel')),
    sa.CheckConstraint('revenue_minor >= 0', name=op.f(f'ck_{table}_revenue_non_negative')),
    sa.CheckConstraint('units >= 0', name=op.f(f'ck_{table}_units_non_negative')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f(f'fk_{table}_product_id_products')),
    sa.ForeignKeyConstraint(['region_id'], ['regions.id'], name=op.f(f'fk_{table}_region_id_regions')),
    sa.PrimaryKeyConstraint('id', name=op.f(f'pk_{table}')),
    sa.UniqueConstraint('period_start', 'product_id', 'region_id', 'channel', name=f'uq_{table}_cell')
    )
    with op.batch_alter_table(table, schema=None) as batch_op:
        batch_op.create_index(f'ix_{table}_product_period', ['product_id', 'period_start'], unique=False)


def upgrade() -> None:
    for table in TABLES:
        _create(table)
    if op.get_bind().dialect.name == 'postgresql':
        for table in TABLES:
            op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    for table in reversed(TABLES):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(f'ix_{table}_product_period')
        op.drop_table(table)
