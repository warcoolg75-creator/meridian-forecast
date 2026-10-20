"""Rebuild daily_sales from sales_order_lines, then the weekly and monthly rollups.

Idempotent by construction: inside one transaction it deletes every order-derived
row in the date range and re-inserts the aggregate. Rows with source='import'
(CSV uploads) are never touched, and order data for a cell that has an imported
row is skipped, so the import stays authoritative for that cell. Row ids are not
stable across rebuilds; nothing should reference daily_sales.id.

weekly_sales and monthly_sales are pure GROUP BYs of daily_sales. Whatever changes
daily_sales (this job, a CSV import) calls rebuild_period_rollups for the dates it
touched, which rebuilds every week and month those dates fall in.
"""

from datetime import date

from sqlalchemy import BigInteger, and_, cast, delete, exists, func, insert, literal, select
from sqlalchemy.orm import Session, aliased

from app.models import DailySales, MonthlySales, SalesOrder, SalesOrderLine, SalesSource, WeeklySales
from app.schemas.imports import PeriodRollupResult, RollupResult
from app.services.bucketing import Granularity, period_end, period_start, period_start_expr

REPORTING_CURRENCY = "INR"


class RollupError(Exception):
    pass


def _in_range(column, date_from: date | None, date_to: date | None) -> list:
    conditions = []
    if date_from:
        conditions.append(column >= date_from)
    if date_to:
        conditions.append(column <= date_to)
    return conditions


def rebuild_daily_sales(session: Session, date_from: date | None = None, date_to: date | None = None) -> RollupResult:
    """Caller owns the transaction (commit/rollback)."""
    order_range = _in_range(SalesOrder.order_date, date_from, date_to)

    foreign = session.scalar(
        select(func.count()).select_from(SalesOrder).where(SalesOrder.currency != REPORTING_CURRENCY, *order_range)
    )
    if foreign:
        # daily_sales.revenue_minor has no currency column; summing mixed currencies would be wrong.
        raise RollupError(f"{foreign} order(s) in range are not in {REPORTING_CURRENCY}; refusing to roll up")

    deleted = session.execute(
        delete(DailySales).where(
            DailySales.source == SalesSource.ORDERS, *_in_range(DailySales.date, date_from, date_to)
        )
    ).rowcount

    imported = aliased(DailySales)
    covered_by_import = exists().where(
        and_(
            imported.source == SalesSource.IMPORT,
            imported.date == SalesOrder.order_date,
            imported.product_id == SalesOrderLine.product_id,
            imported.region_id == SalesOrder.region_id,
            imported.channel == SalesOrder.channel,
        )
    )
    aggregate_columns = (
        SalesOrder.order_date,
        SalesOrderLine.product_id,
        SalesOrder.region_id,
        SalesOrder.channel,
    )
    base = (
        select()
        .select_from(SalesOrderLine)
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .where(*order_range)
    )

    aggregate = (
        base.add_columns(
            *aggregate_columns,
            func.sum(SalesOrderLine.quantity),
            func.sum(
                cast(SalesOrderLine.quantity, BigInteger) * SalesOrderLine.unit_price_minor
                - SalesOrderLine.discount_minor
            ),
            func.count(func.distinct(SalesOrder.id)),
            literal(SalesSource.ORDERS.value),
        )
        .where(~covered_by_import)
        .group_by(*aggregate_columns)
    )
    # SQLAlchemy keeps rowcount only for UPDATE/DELETE unless asked; psycopg 3.3 resets it
    # when the cursor closes, so without preserve_rowcount this reads -1 on PostgreSQL.
    inserted = session.execute(
        insert(DailySales).from_select(
            ["date", "product_id", "region_id", "channel", "units", "revenue_minor", "order_count", "source"],
            aggregate,
        ),
        execution_options={"preserve_rowcount": True},
    ).rowcount

    skipped = session.scalar(
        select(func.count()).select_from(
            base.add_columns(*aggregate_columns).where(covered_by_import).group_by(*aggregate_columns).subquery()
        )
    )
    periods = rebuild_period_rollups(session, date_from, date_to)
    return RollupResult(deleted=deleted, inserted=inserted, skipped_for_imports=skipped or 0,
                        weekly_rows=periods.weekly_rows, monthly_rows=periods.monthly_rows)


PERIOD_TABLES = ((WeeklySales, Granularity.WEEK), (MonthlySales, Granularity.MONTH))


def rebuild_period_rollups(session: Session, date_from: date | None = None,
                           date_to: date | None = None) -> PeriodRollupResult:
    """Rebuild weekly_sales and monthly_sales from daily_sales for every week and month
    that [date_from, date_to] touches (all of them when a bound is None). Idempotent:
    deletes those periods and re-inserts their GROUP BY. Caller owns the transaction."""
    rows = {}
    for model, granularity in PERIOD_TABLES:
        first = period_start(date_from, granularity) if date_from else None
        last = period_start(date_to, granularity) if date_to else None
        session.execute(delete(model).where(*_in_range(model.period_start, first, last)))
        bucket = period_start_expr(DailySales.date, granularity)
        aggregate = (
            select(
                bucket,
                DailySales.product_id,
                DailySales.region_id,
                DailySales.channel,
                func.sum(DailySales.units),
                func.sum(DailySales.revenue_minor),
                func.sum(DailySales.order_count),
            )
            .where(*_in_range(DailySales.date, first, period_end(last, granularity) if last else None))
            .group_by(bucket, DailySales.product_id, DailySales.region_id, DailySales.channel)
        )
        rows[granularity] = session.execute(
            insert(model).from_select(
                ["period_start", "product_id", "region_id", "channel", "units", "revenue_minor", "order_count"],
                aggregate,
            ),
            execution_options={"preserve_rowcount": True},
        ).rowcount
    return PeriodRollupResult(weekly_rows=rows[Granularity.WEEK], monthly_rows=rows[Granularity.MONTH])
