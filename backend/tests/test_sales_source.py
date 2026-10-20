"""Reading whole periods from the rollups and edge days from daily_sales gives exactly
what bucketing daily_sales would."""

from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from app.models import DailySales
from app.services.bucketing import Granularity, period_start_expr, shift_days
from app.services.sales_source import (
    RowFilter,
    Window,
    plan_periods,
    sales_rows,
    shifted_row_selects,
    union_rows,
)
from tests.conftest import add_daily


def test_plan_splits_a_window_into_whole_weeks_and_edges():
    plan = plan_periods(Window(date(2025, 10, 10), date(2026, 10, 8)), Granularity.WEEK)  # Fri .. Thu
    assert plan.whole == (date(2025, 10, 13), date(2026, 9, 28))
    assert plan.edges == (Window(date(2025, 10, 10), date(2025, 10, 12)), Window(date(2026, 10, 5), date(2026, 10, 8)))


def test_plan_for_aligned_and_tiny_windows():
    assert plan_periods(Window(date(2025, 3, 3), date(2025, 3, 30)), Granularity.WEEK).edges == ()
    tiny = plan_periods(Window(date(2025, 3, 4), date(2025, 3, 6)), Granularity.WEEK)
    assert tiny.whole is None and tiny.edges == (Window(date(2025, 3, 4), date(2025, 3, 6)),)
    month = plan_periods(Window(date(2024, 1, 15), date(2024, 3, 31)), Granularity.MONTH)
    assert month.whole == (date(2024, 2, 1), date(2024, 3, 1))
    assert month.edges == (Window(date(2024, 1, 15), date(2024, 1, 31)),)


@pytest.fixture
def ninety_days(db, ids):
    start = date(2024, 12, 20)
    add_daily(db, ids, [
        (start + timedelta(days=k), sku, region, channel, (k * 7 + len(sku)) % 13 + 1, ((k * 7) % 13 + 1) * 333)
        for k in range(90)
        for sku, region, channel in [("FDS-GFB-1KG", "IN-MH-MUM", "retail"), ("IND-BRG-6205", "IN-DL-NDL", "direct"),
                                     ("FDS-GFB-1KG", "IN-MH-PUN", "distributor")]
    ])


@pytest.mark.parametrize("granularity", [Granularity.WEEK, Granularity.MONTH])
@pytest.mark.parametrize(("frm", "to"), [
    (date(2024, 12, 22), date(2025, 3, 10)),
    (date(2025, 1, 1), date(2025, 1, 31)),
    (date(2025, 1, 6), date(2025, 1, 12)),
    (date(2025, 2, 3), date(2025, 2, 4)),
])
def test_hybrid_rows_bucket_like_daily_rows(db, ninety_days, granularity, frm, to):
    def bucketed(rows, date_column):
        bucket = period_start_expr(date_column, granularity)
        return db.execute(
            sa.select(bucket, rows.c.product_id, sa.func.sum(rows.c.units), sa.func.sum(rows.c.revenue_minor))
            .group_by(bucket, rows.c.product_id)
            .order_by(bucket, rows.c.product_id)
        ).all()

    hybrid = sales_rows([Window(frm, to)], granularity, RowFilter())
    raw = sa.select(DailySales).where(DailySales.date.between(frm, to)).subquery()
    assert bucketed(hybrid, hybrid.c.d) == bucketed(raw, raw.c.date)


@pytest.mark.parametrize("granularity", [Granularity.WEEK, Granularity.MONTH])
@pytest.mark.parametrize("shift", [364, 91, 28, 30])
@pytest.mark.parametrize(("frm", "to"), [(date(2024, 12, 20), date(2025, 3, 19)), (date(2025, 1, 2), date(2025, 2, 27))])
def test_shifted_rows_land_in_the_same_buckets_as_daily_rows(db, ninety_days, granularity, shift, frm, to):
    """The comparison series: every row's days, moved `shift` later, bucket exactly as the
    daily rows would, though most weeks are read from weekly_sales."""
    def bucketed(rows, date_column):
        bucket = period_start_expr(shift_days(date_column, shift), granularity)
        return db.execute(
            sa.select(bucket, sa.func.sum(rows.c.units), sa.func.sum(rows.c.revenue_minor))
            .group_by(bucket)
            .order_by(bucket)
        ).all()

    shifted = union_rows(shifted_row_selects(Window(frm, to), shift, granularity, RowFilter(), index=0))
    raw = sa.select(DailySales).where(DailySales.date.between(frm, to)).subquery()
    assert bucketed(shifted, shifted.c.d) == bucketed(raw, raw.c.date)
