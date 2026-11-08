"""forecast runs, forecasts and backtest metrics

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-08

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Row-level security on every new table, as 0002 does for the original ones.
TABLES = ('forecast_runs', 'backtest_metrics', 'forecasts')


def upgrade() -> None:
    # Each Enum has create_constraint=False and its CHECK listed once (autogenerate emits two).
    op.create_table('forecast_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Enum('production', 'backtest', name='forecast_run_kind', native_enum=False, create_constraint=False, length=20), nullable=False),
    sa.Column('model', sa.String(length=40), nullable=False),
    sa.Column('data_end_date', sa.Date(), nullable=False),
    sa.Column('training_cutoff', sa.Date(), nullable=False),
    sa.Column('trained_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('library_versions', sa.JSON(), nullable=False),
    sa.Column('random_seed', sa.Integer(), nullable=False),
    sa.Column('duration_seconds', sa.Float(), nullable=False),
    sa.CheckConstraint("kind IN ('production', 'backtest')", name=op.f('ck_forecast_runs_forecast_run_kind')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_forecast_runs'))
    )
    op.create_table('backtest_metrics',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('model', sa.String(length=40), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('window', sa.Enum('selection', 'held_out', 'festive_2025', name='metric_window', native_enum=False, create_constraint=False, length=20), nullable=False),
    sa.Column('shocks', sa.Enum('included', 'excluded', name='shock_scope', native_enum=False, create_constraint=False, length=20), nullable=False),
    sa.Column('horizon', sa.SmallInteger(), nullable=True),
    sa.Column('n_weeks', sa.Integer(), nullable=False),
    sa.Column('wape', sa.Float(), nullable=True),
    sa.Column('bias', sa.Float(), nullable=True),
    sa.Column('mase', sa.Float(), nullable=True),
    sa.Column('coverage_80', sa.Float(), nullable=True),
    sa.Column('coverage_95', sa.Float(), nullable=True),
    sa.CheckConstraint("shocks IN ('included', 'excluded')", name=op.f('ck_backtest_metrics_shock_scope')),
    sa.CheckConstraint("window IN ('selection', 'held_out', 'festive_2025')", name=op.f('ck_backtest_metrics_metric_window')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_backtest_metrics_product_id_products')),
    sa.ForeignKeyConstraint(['run_id'], ['forecast_runs.id'], name=op.f('fk_backtest_metrics_run_id_forecast_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_backtest_metrics'))
    )
    with op.batch_alter_table('backtest_metrics', schema=None) as batch_op:
        batch_op.create_index('ix_backtest_metrics_run_model', ['run_id', 'model'], unique=False)

    op.create_table('forecasts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('week', sa.Date(), nullable=False),
    sa.Column('horizon', sa.SmallInteger(), nullable=False),
    sa.Column('model', sa.String(length=40), nullable=False),
    sa.Column('p50', sa.Integer(), nullable=False),
    sa.Column('lo80', sa.Integer(), nullable=False),
    sa.Column('hi80', sa.Integer(), nullable=False),
    sa.Column('lo95', sa.Integer(), nullable=False),
    sa.Column('hi95', sa.Integer(), nullable=False),
    sa.CheckConstraint('horizon BETWEEN 1 AND 26', name=op.f('ck_forecasts_horizon_range')),
    sa.CheckConstraint('p50 >= 0 AND lo95 >= 0 AND lo95 <= lo80 AND lo80 <= hi80 AND hi80 <= hi95', name=op.f('ck_forecasts_intervals_ordered')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_forecasts_product_id_products')),
    sa.ForeignKeyConstraint(['run_id'], ['forecast_runs.id'], name=op.f('fk_forecasts_run_id_forecast_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_forecasts')),
    sa.UniqueConstraint('run_id', 'product_id', 'week', name='uq_forecasts_run_product_week')
    )
    with op.batch_alter_table('forecasts', schema=None) as batch_op:
        batch_op.create_index('ix_forecasts_product_run', ['product_id', 'run_id'], unique=False)

    if op.get_bind().dialect.name == 'postgresql':
        for table in TABLES:
            op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    with op.batch_alter_table('forecasts', schema=None) as batch_op:
        batch_op.drop_index('ix_forecasts_product_run')
    op.drop_table('forecasts')
    with op.batch_alter_table('backtest_metrics', schema=None) as batch_op:
        batch_op.drop_index('ix_backtest_metrics_run_model')
    op.drop_table('backtest_metrics')
    op.drop_table('forecast_runs')
