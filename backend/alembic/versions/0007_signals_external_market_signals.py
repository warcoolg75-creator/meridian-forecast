"""signals: external market signals (context only)

Weather, Wikipedia pageviews, input-cost prices and news headlines, with their sources,
fetch runs (provenance) and the series-to-product mapping. Never a forecasting input.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-10

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLES = ('signal_sources', 'signal_fetches', 'signal_series', 'news_items', 'signal_mappings',
          'signal_observations', 'news_item_categories')


def upgrade() -> None:
    # Each Enum has create_constraint=False and its CHECK listed once (autogenerate emits two).
    # No foreign key to products or regions: `make seed` wipes those, never these.
    op.create_table('signal_sources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('homepage', sa.String(length=200), nullable=False),
    sa.Column('licence', sa.String(length=200), nullable=False),
    sa.Column('attribution', sa.String(length=400), nullable=False),
    sa.Column('terms_url', sa.String(length=300), nullable=False),
    sa.Column('requires_key', sa.Boolean(), nullable=False),
    sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_status', sa.Enum('running', 'ok', 'partial', 'failed', 'not_configured', name='fetch_status', native_enum=False, create_constraint=False, length=20), nullable=True),
    sa.Column('last_error', sa.String(length=500), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("last_status IN ('running', 'ok', 'partial', 'failed', 'not_configured')", name=op.f('ck_signal_sources_fetch_status')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_signal_sources')),
    sa.UniqueConstraint('code', name=op.f('uq_signal_sources_code'))
    )
    op.create_table('signal_fetches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('mode', sa.Enum('backfill', 'refresh', name='fetch_mode', native_enum=False, create_constraint=False, length=20), nullable=False),
    sa.Column('status', sa.Enum('running', 'ok', 'partial', 'failed', 'not_configured', name='fetch_status', native_enum=False, create_constraint=False, length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('requests', sa.Integer(), nullable=False),
    sa.Column('inserted', sa.Integer(), nullable=False),
    sa.Column('updated', sa.Integer(), nullable=False),
    sa.Column('deleted', sa.Integer(), nullable=False),
    sa.Column('unchanged', sa.Integer(), nullable=False),
    sa.Column('error', sa.String(length=500), nullable=True),
    sa.Column('cache_dir', sa.String(length=300), nullable=True),
    sa.Column('detail', sa.JSON(), nullable=True),
    sa.CheckConstraint("mode IN ('backfill', 'refresh')", name=op.f('ck_signal_fetches_fetch_mode')),
    sa.CheckConstraint("status IN ('running', 'ok', 'partial', 'failed', 'not_configured')", name=op.f('ck_signal_fetches_fetch_status')),
    sa.ForeignKeyConstraint(['source_id'], ['signal_sources.id'], name=op.f('fk_signal_fetches_source_id_signal_sources')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_signal_fetches'))
    )
    with op.batch_alter_table('signal_fetches', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_signal_fetches_source_id'), ['source_id'], unique=False)

    op.create_table('signal_series',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=False),
    sa.Column('description', sa.String(length=400), nullable=False),
    sa.Column('unit', sa.String(length=60), nullable=False),
    sa.Column('geography', sa.String(length=16), nullable=False),
    sa.Column('geography_name', sa.String(length=80), nullable=False),
    sa.Column('frequency', sa.Enum('daily', 'weekly', 'monthly', name='signal_frequency', native_enum=False, create_constraint=False, length=20), nullable=False),
    sa.Column('aggregation', sa.Enum('mean', 'sum', name='signal_aggregation', native_enum=False, create_constraint=False, length=20), nullable=False),
    sa.Column('role', sa.Enum('demand_context', 'input_cost', name='signal_role', native_enum=False, create_constraint=False, length=20), nullable=False),
    sa.Column('group_key', sa.String(length=40), nullable=False),
    sa.Column('is_forecast', sa.Boolean(), nullable=False),
    sa.Column('companion_key', sa.String(length=80), nullable=True),
    sa.Column('external_id', sa.String(length=120), nullable=False),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('citation', sa.String(length=400), nullable=True),
    sa.Column('stale_after_days', sa.SmallInteger(), nullable=False),
    sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.String(length=500), nullable=True),
    sa.Column('latest_observed_on', sa.Date(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("aggregation IN ('mean', 'sum')", name=op.f('ck_signal_series_signal_aggregation')),
    sa.CheckConstraint("frequency IN ('daily', 'weekly', 'monthly')", name=op.f('ck_signal_series_signal_frequency')),
    sa.CheckConstraint("role IN ('demand_context', 'input_cost')", name=op.f('ck_signal_series_signal_role')),
    sa.ForeignKeyConstraint(['source_id'], ['signal_sources.id'], name=op.f('fk_signal_series_source_id_signal_sources')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_signal_series')),
    sa.UniqueConstraint('key', name=op.f('uq_signal_series_key'))
    )
    with op.batch_alter_table('signal_series', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_signal_series_source_id'), ['source_id'], unique=False)

    op.create_table('news_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('url_hash', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('language', sa.String(length=40), nullable=False),
    sa.Column('publisher', sa.String(length=200), nullable=False),
    sa.Column('source_country', sa.String(length=60), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fetch_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['fetch_id'], ['signal_fetches.id'], name=op.f('fk_news_items_fetch_id_signal_fetches')),
    sa.ForeignKeyConstraint(['source_id'], ['signal_sources.id'], name=op.f('fk_news_items_source_id_signal_sources')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_news_items')),
    sa.UniqueConstraint('url_hash', name=op.f('uq_news_items_url_hash'))
    )
    with op.batch_alter_table('news_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_news_items_fetch_id'), ['fetch_id'], unique=False)
        batch_op.create_index('ix_news_items_published_at', ['published_at'], unique=False)

    op.create_table('signal_mappings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('series_id', sa.Integer(), nullable=False),
    sa.Column('category', sa.String(length=60), nullable=True),
    sa.Column('sku', sa.String(length=32), nullable=True),
    sa.Column('role', sa.Enum('demand_context', 'input_cost', name='signal_role', native_enum=False, create_constraint=False, length=20), nullable=False),
    sa.Column('reason', sa.String(length=400), nullable=False),
    sa.Column('sort_order', sa.SmallInteger(), nullable=False),
    sa.CheckConstraint("role IN ('demand_context', 'input_cost')", name=op.f('ck_signal_mappings_signal_role')),
    sa.CheckConstraint('(category IS NULL) <> (sku IS NULL)', name=op.f('ck_signal_mappings_category_or_sku')),
    sa.ForeignKeyConstraint(['series_id'], ['signal_series.id'], name=op.f('fk_signal_mappings_series_id_signal_series'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_signal_mappings'))
    )
    with op.batch_alter_table('signal_mappings', schema=None) as batch_op:
        batch_op.create_index('ix_signal_mappings_category', ['category'], unique=False)
        batch_op.create_index('ix_signal_mappings_sku', ['sku'], unique=False)

    op.create_table('signal_observations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('series_id', sa.Integer(), nullable=False),
    sa.Column('observed_on', sa.Date(), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fetch_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['fetch_id'], ['signal_fetches.id'], name=op.f('fk_signal_observations_fetch_id_signal_fetches')),
    sa.ForeignKeyConstraint(['series_id'], ['signal_series.id'], name=op.f('fk_signal_observations_series_id_signal_series'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_signal_observations')),
    sa.UniqueConstraint('series_id', 'observed_on', name='uq_signal_observations_series_day')
    )
    with op.batch_alter_table('signal_observations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_signal_observations_fetch_id'), ['fetch_id'], unique=False)

    op.create_table('news_item_categories',
    sa.Column('news_item_id', sa.Integer(), nullable=False),
    sa.Column('category', sa.String(length=60), nullable=False),
    sa.ForeignKeyConstraint(['news_item_id'], ['news_items.id'], name=op.f('fk_news_item_categories_news_item_id_news_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('news_item_id', 'category', name=op.f('pk_news_item_categories'))
    )
    with op.batch_alter_table('news_item_categories', schema=None) as batch_op:
        batch_op.create_index('ix_news_item_categories_category', ['category'], unique=False)


    if op.get_bind().dialect.name == 'postgresql':
        for table in TABLES:
            op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    with op.batch_alter_table('news_item_categories', schema=None) as batch_op:
        batch_op.drop_index('ix_news_item_categories_category')

    op.drop_table('news_item_categories')
    with op.batch_alter_table('signal_observations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_signal_observations_fetch_id'))

    op.drop_table('signal_observations')
    with op.batch_alter_table('signal_mappings', schema=None) as batch_op:
        batch_op.drop_index('ix_signal_mappings_sku')
        batch_op.drop_index('ix_signal_mappings_category')

    op.drop_table('signal_mappings')
    with op.batch_alter_table('news_items', schema=None) as batch_op:
        batch_op.drop_index('ix_news_items_published_at')
        batch_op.drop_index(batch_op.f('ix_news_items_fetch_id'))

    op.drop_table('news_items')
    with op.batch_alter_table('signal_series', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_signal_series_source_id'))

    op.drop_table('signal_series')
    with op.batch_alter_table('signal_fetches', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_signal_fetches_source_id'))

    op.drop_table('signal_fetches')
    op.drop_table('signal_sources')
