"""weekly_sales and monthly_sales always equal the GROUP BY of daily_sales.

Whatever writes daily_sales (the rollup job, a CSV import) rebuilds the weeks and months
it touched in the same transaction; analytics reads whole periods from these tables.
"""

from datetime import date, timedelta

import sqlalchemy as sa

from app import cli
from app.models import DailySales, MonthlySales, WeeklySales
from app.services.bucketing import Granularity, period_start_expr
from app.services.csv_import import import_sales_csv
from app.services.rollup import rebuild_daily_sales, rebuild_period_rollups
from tests.conftest import add_daily, add_order

TABLES = ((WeeklySales, Granularity.WEEK), (MonthlySales, Granularity.MONTH))


def rollup_content(db, model) -> list[tuple]:
    db.expire_all()
    return [tuple(r) for r in db.execute(sa.select(
        model.period_start, model.product_id, model.region_id, model.channel, model.units,
        model.revenue_minor, model.order_count,
    ).order_by(model.period_start, model.product_id, model.region_id, model.channel)).all()]


def grouped_daily(db, granularity) -> list[tuple]:
    bucket = period_start_expr(DailySales.date, granularity)
    return [tuple(r) for r in db.execute(sa.select(
        bucket, DailySales.product_id, DailySales.region_id, DailySales.channel, sa.func.sum(DailySales.units),
        sa.func.sum(DailySales.revenue_minor), sa.func.sum(DailySales.order_count),
    ).group_by(bucket, DailySales.product_id, DailySales.region_id, DailySales.channel)
     .order_by(bucket, DailySales.product_id, DailySales.region_id, DailySales.channel)).all()]


def assert_rollups_match(db):
    for model, granularity in TABLES:
        assert rollup_content(db, model) == grouped_daily(db, granularity), model.__tablename__


def test_rollup_job_rebuilds_weeks_and_months(db, ids):
    for day in (date(2025, 1, 30), date(2025, 1, 31), date(2025, 2, 1), date(2025, 2, 3)):
        add_order(db, ids, day, "C01", "IN-MH-MUM", "distributor",
                  [("FDS-GFB-1KG", day.day, 1000, 0), ("IND-BRG-6205", 2, 150, 0)])
    result = rebuild_daily_sales(db)
    db.commit()
    assert (result.weekly_rows, result.monthly_rows) == (4, 4)  # 2 weeks x 2 products, 2 months x 2
    assert_rollups_match(db)


def test_partial_rebuild_only_touches_the_periods_in_range(db, ids):
    add_daily(db, ids, [(date(2025, 1, 6) + timedelta(days=k), "FDS-GFB-1KG", "IN-MH-MUM", "retail", 1, 100)
                        for k in range(60)])
    assert_rollups_match(db)
    # Change one day directly, then rebuild only that day: its week and month follow,
    # the other periods keep their rows.
    db.execute(sa.update(DailySales).where(DailySales.date == date(2025, 2, 12)).values(units=50))
    before = rollup_content(db, WeeklySales)
    rebuild_period_rollups(db, date(2025, 2, 12), date(2025, 2, 12))
    db.commit()
    after = rollup_content(db, WeeklySales)
    changed = [a for a, b in zip(after, before, strict=True) if a != b]
    assert [row[0] for row in changed] == [date(2025, 2, 10)]
    assert_rollups_match(db)


def test_rebuild_is_idempotent(db, ids):
    add_daily(db, ids, [(date(2025, 3, 1), "IND-BRG-6205", "IN-DL-NDL", "direct", 5, 925)])
    first = rollup_content(db, MonthlySales)
    rebuild_period_rollups(db)
    rebuild_period_rollups(db)
    db.commit()
    assert rollup_content(db, MonthlySales) == first


def test_csv_import_keeps_the_rollups_in_step(db, ids):
    add_daily(db, ids, [(date(2026, 1, 12), "FDS-GFB-1KG", "IN-DL-NDL", "retail", 3, 3000)])
    raw = (b"date,sku,region_code,channel,units,revenue\n"
           b"2026-01-14,FDS-GFB-1KG,IN-DL-NDL,retail,12,14388.00\n"
           b"2026-02-02,IND-BRG-6205,IN-MH-PUN,direct,4,740.00\n")
    report = import_sales_csv(db, raw)
    assert report.status == "imported"
    assert_rollups_match(db)
    week = db.execute(sa.select(WeeklySales.units).where(WeeklySales.period_start == date(2026, 1, 12))).scalar()
    assert week == 15


def test_rollup_periods_command_leaves_daily_sales_alone(db, ids, monkeypatch, capsys):
    add_daily(db, ids, [(date(2025, 5, 5), "FDS-GFB-1KG", "IN-MH-MUM", "retail", 2, 200)])
    db.execute(sa.delete(WeeklySales))
    db.execute(sa.delete(MonthlySales))
    db.commit()
    daily_before = db.scalar(sa.select(sa.func.count()).select_from(DailySales))

    monkeypatch.setattr(cli, "get_sessionmaker", lambda: (lambda: sa.orm.Session(db.get_bind())))
    assert cli.main(["rollup-periods"]) == 0
    assert "daily_sales untouched" in capsys.readouterr().out
    assert db.scalar(sa.select(sa.func.count()).select_from(DailySales)) == daily_before
    assert_rollups_match(db)
