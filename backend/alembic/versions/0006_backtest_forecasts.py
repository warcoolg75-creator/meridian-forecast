"""backtest forecasts: a backtest's held-out champion forecasts, horizons 1-4

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ('backtest_forecasts',)


def upgrade() -> None:
    op.create_table('backtest_forecasts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('origin', sa.Date(), nullable=False),
    sa.Column('horizon', sa.SmallInteger(), nullable=False),
    sa.Column('week', sa.Date(), nullable=False),
    sa.Column('model', sa.String(length=40), nullable=False),
    sa.Column('actual', sa.Integer(), nullable=False),
    sa.Column('p50', sa.Float(), nullable=False),
    sa.Column('lo80', sa.Float(), nullable=False),
    sa.Column('hi80', sa.Float(), nullable=False),
    sa.Column('lo95', sa.Float(), nullable=False),
    sa.Column('hi95', sa.Float(), nullable=False),
    sa.CheckConstraint('horizon BETWEEN 1 AND 26', name=op.f('ck_backtest_forecasts_horizon_range')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_backtest_forecasts_product_id_products')),
    sa.ForeignKeyConstraint(['run_id'], ['forecast_runs.id'], name=op.f('fk_backtest_forecasts_run_id_forecast_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_backtest_forecasts')),
    sa.UniqueConstraint('run_id', 'product_id', 'origin', 'horizon', name='uq_backtest_forecasts_key')
    )
    with op.batch_alter_table('backtest_forecasts', schema=None) as batch_op:
        batch_op.create_index('ix_backtest_forecasts_product_run', ['product_id', 'run_id'], unique=False)

    if op.get_bind().dialect.name == 'postgresql':
        for table in TABLES:
            op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    with op.batch_alter_table('backtest_forecasts', schema=None) as batch_op:
        batch_op.drop_index('ix_backtest_forecasts_product_run')
    op.drop_table('backtest_forecasts')
