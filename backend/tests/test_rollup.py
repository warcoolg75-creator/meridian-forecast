"""Rollup job: daily_sales rebuilt from sales_order_lines, idempotently."""

from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from app import cli
from app.models import DailySales, SalesOrder, SalesOrderLine
from app.services.rollup import RollupError, rebuild_daily_sales
from tests.conftest import add_daily, add_order

DAY1, DAY2 = date(2025, 3, 10), date(2025, 3, 11)


@pytest.fixture
def orders(db, ids):
    """Two days of orders across customers, regions, channels and a promo line."""
    return {
        "a": add_order(db, ids, DAY1, "C01", "IN-MH-MUM", "distributor",
                       [("FDS-GFB-1KG", 10, 1000, 0), ("IND-BRG-6205", 200, 150, 0)]),
        "b": add_order(db, ids, DAY1, "C01", "IN-MH-MUM", "distributor", [("FDS-GFB-1KG", 5, 1000, 500)]),
        # Ecommerce customer in Mumbai shipping to New Delhi: the order's region wins.
        "c": add_order(db, ids, DAY1, "C16", "IN-DL-NDL", "ecommerce", [("FDS-GFB-1KG", 2, 1100, 0)]),
        "d": add_order(db, ids, DAY2, "C09", "IN-DL-NDL", "retail", [("FDS-GFB-1KG", 7, 1050, 735)]),
    }


def snapshot(db) -> list[tuple]:
    """daily_sales content without the surrogate id."""
    db.expire_all()
    return [tuple(r) for r in db.execute(sa.select(
        DailySales.date, DailySales.product_id, DailySales.region_id, DailySales.channel, DailySales.units,
        DailySales.revenue_minor, DailySales.order_count, DailySales.source,
    ).order_by(DailySales.date, DailySales.product_id, DailySales.region_id, DailySales.channel)).all()]


def rollup(db, **kwargs):
    result = rebuild_daily_sales(db, **kwargs)
    db.commit()
    return result


def test_rollup_aggregates_order_lines(db, ids, orders):
    result = rollup(db)
    gfb, brg = ids["product"]["FDS-GFB-1KG"], ids["product"]["IND-BRG-6205"]
    mum, ndl = ids["region"]["IN-MH-MUM"], ids["region"]["IN-DL-NDL"]

    assert snapshot(db) == [
        (DAY1, gfb, mum, "distributor", 15, 10 * 1000 + 5 * 1000 - 500, 2, "orders"),
        (DAY1, gfb, ndl, "ecommerce", 2, 2200, 1, "orders"),
        (DAY1, brg, mum, "distributor", 200, 30000, 1, "orders"),
        (DAY2, gfb, ndl, "retail", 7, 7 * 1050 - 735, 1, "orders"),
    ]
    assert (result.deleted, result.inserted, result.skipped_for_imports) == (0, 4, 0)


def test_rollup_is_idempotent(db, orders):
    rollup(db)
    first = snapshot(db)
    second_result = rollup(db)
    third_result = rollup(db)

    assert snapshot(db) == first
    assert (second_result.deleted, second_result.inserted) == (4, 4)
    assert (third_result.deleted, third_result.inserted) == (4, 4)


def test_rollup_reflects_changed_and_deleted_orders(db, ids, orders):
    rollup(db)
    db.execute(sa.update(SalesOrderLine).where(SalesOrderLine.sales_order_id == orders["d"]).values(quantity=9))
    db.execute(sa.delete(SalesOrderLine).where(SalesOrderLine.sales_order_id == orders["c"]))
    db.execute(sa.delete(SalesOrder).where(SalesOrder.id == orders["c"]))
    db.commit()
    rollup(db)

    rows = snapshot(db)
    assert len(rows) == 3
    assert rows[-1][4:6] == (9, 9 * 1050 - 735)
    assert not any(r[3] == "ecommerce" for r in rows)


def test_rollup_never_touches_imported_rows(db, ids, orders):
    # One imported cell overlaps order data (DAY2 retail gift box), one does not.
    add_daily(db, ids, [(DAY2, "FDS-GFB-1KG", "IN-DL-NDL", "retail", 99, 123400, "import"),
                        (DAY2, "IND-BRG-6205", "IN-MH-PUN", "direct", 50, 7500, "import")])
    before = [r for r in snapshot(db) if r[7] == "import"]

    result = rollup(db)
    again = rollup(db)

    after = snapshot(db)
    assert [r for r in after if r[7] == "import"] == before
    assert len([r for r in after if r[7] == "orders"]) == 3  # DAY2 retail cell is covered by the import
    assert result.skipped_for_imports == again.skipped_for_imports == 1


def test_rollup_date_range_only_rebuilds_that_range(db, ids, orders):
    rollup(db)
    db.execute(sa.update(SalesOrderLine).values(quantity=SalesOrderLine.quantity + 1))
    db.commit()

    result = rollup(db, date_from=DAY2, date_to=DAY2)

    rows = snapshot(db)
    day1_units = sorted(r[4] for r in rows if r[0] == DAY1)
    day2_units = [r[4] for r in rows if r[0] == DAY2]
    assert day1_units == [2, 15, 200]  # stale on purpose: outside the rebuilt range
    assert day2_units == [8]
    assert (result.deleted, result.inserted) == (1, 1)


def test_rollup_refuses_mixed_currencies(db, ids, orders):
    add_order(db, ids, DAY2, "C01", "IN-MH-MUM", "export", [("IND-BRG-6205", 1, 200, 0)], currency="USD")
    with pytest.raises(RollupError, match="not in INR"):
        rebuild_daily_sales(db)
    db.rollback()
    assert snapshot(db) == []


def test_rollup_cli_entry_point(db, engine, orders, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_sessionmaker", lambda: sessionmaker(bind=engine))

    assert cli.main(["rollup"]) == 0
    assert cli.main(["rollup", "--date-from", "2025-03-11", "--date-to", "2025-03-11"]) == 0

    output = capsys.readouterr().out
    assert "inserted 4" in output and "2025-03-11 .. 2025-03-11" in output
    assert len(snapshot(db)) == 4
