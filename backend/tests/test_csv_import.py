"""POST /api/v1/imports/sales and GET /api/v1/imports/sales/template.

The import requires an admin or planner (the role guard itself is tested in
test_auth.py); every test here signs the client in as a planner.
"""

from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from app.models import DailySales, UserRole
from app.services.csv_import import COLUMNS
from app.services.rollup import rebuild_daily_sales
from tests.conftest import add_daily, add_order

HEADER = "date,sku,region_code,channel,units,revenue"
GOOD_1 = "2025-01-15,FDS-GFB-1KG,IN-DL-NDL,retail,12,14388.00"
GOOD_2 = "2025-01-15,IND-BRG-6205,IN-MH-PUN,distributor,400,60680.5"
TOMORROW = (date.today() + timedelta(days=2)).isoformat()


@pytest.fixture(autouse=True)
def _signed_in_as_planner(client, auth_headers):
    client.headers.update(auth_headers(UserRole.PLANNER))


def upload(client, text: str | bytes):
    content = text.encode() if isinstance(text, str) else text
    return client.post("/api/v1/imports/sales", files={"file": ("sales.csv", content, "text/csv")})


def daily_rows(db) -> list[tuple]:
    db.expire_all()
    return [tuple(r) for r in db.execute(sa.select(
        DailySales.date, DailySales.product_id, DailySales.region_id, DailySales.channel, DailySales.units,
        DailySales.revenue_minor, DailySales.order_count, DailySales.source,
    ).order_by(DailySales.id)).all()]


@pytest.fixture
def existing(db, ids):
    """One pre-existing row that a rejected import must leave untouched."""
    add_daily(db, ids, [(date(2025, 1, 15), "FDS-GFB-1KG", "IN-DL-NDL", "retail", 3, 3000)])
    return daily_rows(db)


MALFORMED = [
    pytest.param("2025/01/15,FDS-GFB-1KG,IN-DL-NDL,retail,1,10", "date", "ISO date", id="date-format"),
    pytest.param("2025-02-30,FDS-GFB-1KG,IN-DL-NDL,retail,1,10", "date", "real calendar date", id="impossible-date"),
    pytest.param(f"{TOMORROW},FDS-GFB-1KG,IN-DL-NDL,retail,1,10", "date", "future", id="future-date"),
    pytest.param("2025-12-01,KIT-AFR-45,IN-DL-NDL,retail,1,10", "date", "before the product launched",
                 id="before-launch"),
    pytest.param("2025-01-16,NOPE-1,IN-DL-NDL,retail,1,10", "sku", "Unknown sku", id="unknown-sku"),
    pytest.param("2025-01-16,FDS-GFB-1KG,IN-XX,retail,1,10", "region_code", "Unknown region", id="unknown-region"),
    pytest.param("2025-01-16,FDS-GFB-1KG,IN-DL-NDL,wholesale,1,10", "channel", "Must be one of", id="bad-channel"),
    pytest.param("2025-01-16,FDS-GFB-1KG,IN-DL-NDL,retail,-3,10", "units", "whole number", id="negative-units"),
    pytest.param("2025-01-16,FDS-GFB-1KG,IN-DL-NDL,retail,2.5,10", "units", "whole number", id="fractional-units"),
    pytest.param("2025-01-16,FDS-GFB-1KG,IN-DL-NDL,retail,,10", "units", "whole number", id="empty-units"),
    pytest.param("2025-01-16,FDS-GFB-1KG,IN-DL-NDL,retail,1,10.555", "revenue", "at most 2 decimals",
                 id="revenue-3dp"),
    pytest.param('2025-01-16,FDS-GFB-1KG,IN-DL-NDL,retail,1,"1,234.00"', "revenue", "no separators",
                 id="revenue-thousands-separator"),
    pytest.param("2025-01-16,FDS-GFB-1KG,IN-DL-NDL,retail,1,-5", "revenue", "non-negative", id="negative-revenue"),
    pytest.param("2025-01-16,FDS-GFB-1KG,IN-DL-NDL,retail,1", None, "Expected 6 fields, got 5", id="missing-field"),
]


@pytest.mark.parametrize(("bad_line", "column", "message"), MALFORMED)
def test_malformed_row_rejects_the_whole_file(client, db, existing, bad_line, column, message):
    response = upload(client, "\n".join([HEADER, GOOD_1.replace("12,", "50,"), bad_line, GOOD_2]) + "\n")

    assert response.status_code == 422
    report = response.json()
    assert report["status"] == "rejected"
    assert (report["rows_received"], report["rows_valid"], report["inserted"], report["updated"]) == (3, 2, 0, 0)
    assert [(e["row"], e["column"]) for e in report["errors"]] == [(3, column)]
    assert message in report["errors"][0]["message"]
    assert daily_rows(db) == existing  # nothing imported, existing row not updated


def test_every_problem_is_reported_with_its_row(client, db, existing):
    body = "\n".join([
        HEADER,
        GOOD_1,
        "2025-01-16,NOPE-1,IN-DL-NDL,retail,x,10",  # two problems on one row
        GOOD_2,
        GOOD_1.replace("12,", "13,"),  # same key as row 2
    ])
    report = upload(client, body).json()

    assert [(e["row"], e["column"]) for e in report["errors"]] == [(3, "sku"), (3, "units"), (5, None)]
    assert report["errors"][2]["message"].startswith("Duplicate of row 2")
    assert report["error_count"] == 3 and not report["errors_truncated"]
    assert daily_rows(db) == existing


@pytest.mark.parametrize(("content", "message"), [
    pytest.param(b"", "File is empty", id="empty"),
    pytest.param(HEADER.encode() + b"\n", "no data rows", id="header-only"),
    pytest.param(b"date,sku,units\n2025-01-15,FDS-GFB-1KG,1\n", "Required column is missing", id="missing-columns"),
    pytest.param((HEADER + ",notes\n" + GOOD_1 + ",x\n").encode(), "Unknown column", id="extra-column"),
    pytest.param(b"date,sku,region_code,channel,units,revenue\n2025-01-15,\xff\xfe,IN-DL-NDL,retail,1,1\n",
                 "not valid UTF-8", id="not-utf8"),
])
def test_file_level_problems(client, db, existing, content, message):
    response = upload(client, content)
    assert response.status_code == 422
    assert message in " ".join(e["message"] for e in response.json()["errors"])
    assert daily_rows(db) == existing


def test_valid_file_upserts_into_daily_sales(client, db, ids):
    first = upload(client, f"﻿{HEADER}\n{GOOD_1}\n{GOOD_2}\n\n")  # BOM and trailing blank line are fine
    assert first.status_code == 200
    assert {k: first.json()[k] for k in ("status", "rows_received", "inserted", "updated")} == {
        "status": "imported", "rows_received": 2, "inserted": 2, "updated": 0}

    second = upload(client, f"{HEADER}\n{GOOD_1.replace('12,14388.00', '20,23980')}\n"
                            "2025-01-16,FDS-GFB-1KG,IN-DL-NDL,Retail,1,1199\n")
    assert (second.json()["inserted"], second.json()["updated"]) == (1, 1)

    gfb, brg = ids["product"]["FDS-GFB-1KG"], ids["product"]["IND-BRG-6205"]
    ndl, pun = ids["region"]["IN-DL-NDL"], ids["region"]["IN-MH-PUN"]
    assert daily_rows(db) == [
        (date(2025, 1, 15), gfb, ndl, "retail", 20, 2398000, None, "import"),
        (date(2025, 1, 15), brg, pun, "distributor", 400, 6068050, None, "import"),
        (date(2025, 1, 16), gfb, ndl, "retail", 1, 119900, None, "import"),
    ]


def test_import_overrides_order_data_and_survives_the_rollup(client, db, ids):
    add_order(db, ids, date(2025, 1, 15), "C09", "IN-DL-NDL", "retail", [("FDS-GFB-1KG", 4, 1000, 0)])
    rebuild_daily_sales(db)
    db.commit()

    report = upload(client, f"{HEADER}\n{GOOD_1}\n").json()
    rebuild_daily_sales(db)
    db.commit()

    assert (report["inserted"], report["updated"]) == (0, 1)
    assert [(r[4], r[5], r[7]) for r in daily_rows(db)] == [(12, 1438800, "import")]


def test_template_downloads_and_imports_cleanly(client, db, ids):
    response = client.get("/api/v1/imports/sales/template")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.text.splitlines()[0] == ",".join(COLUMNS)
    assert upload(client, response.text).status_code == 200
