"""Week/month bucketing must give identical results on SQLite and PostgreSQL.

Each dialect compiles its own SQL (app/services/bucketing.py). These tests run the
SQL on real databases against dates chosen to break naive implementations: ISO week
53, Sunday/Monday edges, leap day, a week straddling New Year. The PostgreSQL tests
run only with MERIDIAN_PG_TESTS=1 (see conftest.py).
"""

from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.seed.generate import wipe_all
from app.services.bucketing import Granularity, period_start, period_start_expr, shift_days
from app.services.sales_query import GroupBy, SalesQuery, query_sales
from tests.conftest import add_daily, add_reference_data, requires_pg

TRICKY_DATES = [
    date(2022, 12, 31),  # Saturday; its ISO week starts in December
    date(2023, 1, 1),  # Sunday -> week of Mon 2022-12-26
    date(2023, 1, 2),  # Monday
    date(2024, 2, 29),  # leap day, Thursday
    date(2024, 3, 3),  # Sunday
    date(2024, 3, 4),  # Monday
    date(2024, 12, 29),  # Sunday
    date(2024, 12, 30),  # Monday of ISO week 1 of 2025
    date(2025, 1, 1),  # Wednesday
    date(2025, 1, 5),  # Sunday
    date(2026, 12, 31),  # Thursday of ISO week 53
    date(2027, 1, 3),  # Sunday, still ISO week 53 of 2026
    date(2027, 1, 4),  # Monday
]
BUCKETED = [Granularity.WEEK, Granularity.MONTH]


def bucket_in_database(engine: Engine, granularity: Granularity) -> list[tuple[date, date]]:
    """Run the dialect's bucketing SQL over TRICKY_DATES; returns (date, period_start) pairs."""
    probe = sa.Table("bucket_probe", sa.MetaData(), sa.Column("d", sa.Date, primary_key=True))
    probe.drop(engine, checkfirst=True)
    probe.create(engine)
    try:
        with engine.begin() as connection:
            connection.execute(probe.insert(), [{"d": d} for d in TRICKY_DATES])
            expr = period_start_expr(probe.c.d, granularity)
            return [tuple(row) for row in connection.execute(sa.select(probe.c.d, expr).order_by(probe.c.d))]
    finally:
        probe.drop(engine)


@pytest.mark.parametrize("granularity", BUCKETED)
def test_sqlite_bucketing_matches_python_reference(sqlite_engine, granularity):
    expected = [(d, period_start(d, granularity)) for d in TRICKY_DATES]
    assert bucket_in_database(sqlite_engine, granularity) == expected


@requires_pg
@pytest.mark.parametrize("granularity", BUCKETED)
def test_postgres_bucketing_matches_python_reference(pg_engine, granularity):
    expected = [(d, period_start(d, granularity)) for d in TRICKY_DATES]
    assert bucket_in_database(pg_engine, granularity) == expected


@requires_pg
@pytest.mark.parametrize("granularity", BUCKETED)
def test_bucketing_identical_on_sqlite_and_postgres(sqlite_engine, pg_engine, granularity):
    assert bucket_in_database(sqlite_engine, granularity) == bucket_in_database(pg_engine, granularity)


@requires_pg
@pytest.mark.parametrize("granularity", [Granularity.DAY, *BUCKETED])
def test_sales_query_identical_on_sqlite_and_postgres(sqlite_engine, pg_engine, granularity):
    """The full /sales/daily query (sums, grouping, partial flags) on the same input rows."""
    results = []
    for engine in (sqlite_engine, pg_engine):
        with Session(engine) as session:
            try:
                ids = add_reference_data(session)
                add_daily(session, ids, [
                    (d, sku, region, channel, units + d.day, (units + d.day) * 100)
                    for d in TRICKY_DATES
                    for sku, region, channel, units in [("FDS-GFB-1KG", "IN-MH-MUM", "retail", 3),
                                                        ("IND-BRG-6205", "IN-DL-NDL", "direct", 40)]
                ])
                query = SalesQuery(granularity=granularity, region_codes=["IN"], group_by=[GroupBy.SKU])
                items, next_cursor = query_sales(session, query, limit=1000)
                results.append(([i.model_dump() for i in items], len(items), next_cursor))
            finally:
                session.rollback()
                wipe_all(session)
                session.commit()
    assert results[0] == results[1]
    assert results[0][1] > 0


SHIFTS = [364, -364, 7, -1, 28]


def shift_in_database(engine: Engine, days: int) -> list[tuple[date, date]]:
    probe = sa.Table("bucket_probe", sa.MetaData(), sa.Column("d", sa.Date, primary_key=True))
    probe.drop(engine, checkfirst=True)
    probe.create(engine)
    try:
        with engine.begin() as connection:
            connection.execute(probe.insert(), [{"d": d} for d in TRICKY_DATES])
            return [tuple(row) for row in connection.execute(
                sa.select(probe.c.d, shift_days(probe.c.d, days)).order_by(probe.c.d))]
    finally:
        probe.drop(engine)


@pytest.mark.parametrize("days", SHIFTS)
def test_sqlite_add_days_matches_python(sqlite_engine, days):
    assert shift_in_database(sqlite_engine, days) == [(d, d + timedelta(days=days)) for d in TRICKY_DATES]


@requires_pg
@pytest.mark.parametrize("days", SHIFTS)
def test_postgres_add_days_matches_python(pg_engine, days):
    assert shift_in_database(pg_engine, days) == [(d, d + timedelta(days=days)) for d in TRICKY_DATES]


def test_different_shifts_do_not_share_a_cached_statement(sqlite_engine):
    """n is inlined in the SQL, so a cached plan for 364 must not answer for 7."""
    assert shift_in_database(sqlite_engine, 364) != shift_in_database(sqlite_engine, 7)
