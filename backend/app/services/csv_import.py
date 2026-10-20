"""CSV import of daily sales: validate every row, then upsert all-or-nothing.

Format (UTF-8, optional BOM, comma-separated, header required):
    date,sku,region_code,channel,units,revenue
    2026-01-15,FDS-GFB-1KG,IN-DL-NDL,retail,12,14388.00

* date        ISO-8601 YYYY-MM-DD, not in the future (UTC), not before the product launched
* sku         an existing product
* region_code an existing region (any level)
* channel     distributor | retail | ecommerce | direct | export
* units       whole number >= 0
* revenue     rupees, >= 0, at most 2 decimal places, no thousands separators;
              stored as paise in revenue_minor

Each (date, sku, region_code, channel) may appear once per file. Imported rows are
upserted into daily_sales with source='import' and order_count NULL, and the
rollup never overwrites them.
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select, tuple_
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.models import Channel, DailySales, Product, Region, SalesSource
from app.schemas.imports import ImportReport, ImportRowError
from app.services.rollup import rebuild_period_rollups

COLUMNS = ("date", "sku", "region_code", "channel", "units", "revenue")
TEMPLATE_CSV = ",".join(COLUMNS) + "\n2026-01-15,FDS-GFB-1KG,IN-DL-NDL,retail,12,14388.00\n"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_REPORTED_ERRORS = 1000
UPSERT_CHUNK = 5000
KEY_LOOKUP_CHUNK = 1000  # 4 bound params per key; stays well under SQLite and PostgreSQL limits

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UNITS_RE = re.compile(r"^\d{1,9}$")
_REVENUE_RE = re.compile(r"^\d{1,13}(\.\d{1,2})?$")
_CHANNELS = {c.value for c in Channel}


@dataclass(frozen=True)
class _ValidRow:
    date: date
    product_id: int
    region_id: int
    channel: Channel
    units: int
    revenue_minor: int


def _rejected(rows_received: int, rows_valid: int, errors: list[ImportRowError]) -> ImportReport:
    return ImportReport(
        status="rejected",
        rows_received=rows_received,
        rows_valid=rows_valid,
        inserted=0,
        updated=0,
        error_count=len(errors),
        errors_truncated=len(errors) > MAX_REPORTED_ERRORS,
        errors=errors[:MAX_REPORTED_ERRORS],
    )


def file_too_large_report() -> ImportReport:
    return _rejected(0, 0, [ImportRowError(row=None, column=None, value=None,
                                           message=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")])


def import_sales_csv(session: Session, raw: bytes, today: date | None = None) -> ImportReport:
    today = today or datetime.now(UTC).date()

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return _rejected(0, 0, [ImportRowError(row=None, column=None, value=None,
                                               message=f"File is not valid UTF-8 ({exc.reason} at byte {exc.start})")])

    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, None)
    if header is None or not any(cell.strip() for cell in header):
        return _rejected(0, 0, [ImportRowError(row=None, column=None, value=None, message="File is empty")])

    header = [cell.strip().lower() for cell in header]
    header_errors = []
    for column in COLUMNS:
        if column not in header:
            header_errors.append(ImportRowError(row=1, column=column, value=None, message="Required column is missing"))
    for column in header:
        if column not in COLUMNS:
            header_errors.append(ImportRowError(row=1, column=column or None, value=column,
                                                message=f"Unknown column; expected exactly: {','.join(COLUMNS)}"))
        elif header.count(column) > 1:
            header_errors.append(ImportRowError(row=1, column=column, value=None, message="Duplicate column"))
    if header_errors:
        return _rejected(0, 0, _dedupe(header_errors))

    index = {column: header.index(column) for column in COLUMNS}
    products = {row.sku: (row.id, row.launched_on) for row in session.execute(
        select(Product.sku, Product.id, Product.launched_on))}
    regions = {row.code: row.id for row in session.execute(select(Region.code, Region.id))}

    errors: list[ImportRowError] = []
    valid: list[_ValidRow] = []
    first_seen: dict[tuple, int] = {}
    rows_received = 0

    for line_number, cells in enumerate(reader, start=2):
        if not any(cell.strip() for cell in cells):
            continue  # blank lines (e.g. a trailing newline) are not data
        rows_received += 1
        if len(cells) != len(header):
            errors.append(ImportRowError(row=line_number, column=None, value=None,
                                         message=f"Expected {len(header)} fields, got {len(cells)}"))
            continue

        values = {column: cells[index[column]].strip() for column in COLUMNS}
        row_errors: list[ImportRowError] = []

        def fail(column: str, message: str) -> None:
            row_errors.append(ImportRowError(row=line_number, column=column, value=values[column], message=message))

        row_date = None
        if not _DATE_RE.match(values["date"]):
            fail("date", "Must be an ISO date YYYY-MM-DD")
        else:
            try:
                row_date = date.fromisoformat(values["date"])
            except ValueError:
                fail("date", "Not a real calendar date")
        if row_date and row_date > today:
            fail("date", f"Is in the future (today is {today.isoformat()} UTC)")

        product = products.get(values["sku"])
        if product is None:
            fail("sku", "Unknown sku")
        elif row_date and row_date < product[1]:
            fail("date", f"Is before the product launched on {product[1].isoformat()}")

        region_id = regions.get(values["region_code"])
        if region_id is None:
            fail("region_code", "Unknown region code")

        channel = values["channel"].lower()
        if channel not in _CHANNELS:
            fail("channel", f"Must be one of: {', '.join(sorted(_CHANNELS))}")

        if not _UNITS_RE.match(values["units"]):
            fail("units", "Must be a whole number >= 0")

        if not _REVENUE_RE.match(values["revenue"]):
            fail("revenue", "Must be a non-negative rupee amount with at most 2 decimals and no "
                            "separators or symbols, e.g. 14388.50")

        if not row_errors:
            key = (row_date, values["sku"], values["region_code"], channel)
            if key in first_seen:
                row_errors.append(ImportRowError(
                    row=line_number, column=None, value=None,
                    message=f"Duplicate of row {first_seen[key]} (same date, sku, region_code, channel)"))
            else:
                first_seen[key] = line_number

        if row_errors:
            errors.extend(row_errors)
            continue
        valid.append(_ValidRow(
            date=row_date,
            product_id=product[0],
            region_id=region_id,
            channel=Channel(channel),
            units=int(values["units"]),
            revenue_minor=int(Decimal(values["revenue"]) * 100),
        ))

    if errors:
        return _rejected(rows_received, len(valid), errors)
    if not valid:
        return _rejected(0, 0, [ImportRowError(row=None, column=None, value=None, message="File has no data rows")])

    inserted, updated = _upsert(session, valid)
    # Same transaction: the weekly and monthly rollups never disagree with daily_sales.
    rebuild_period_rollups(session, min(row.date for row in valid), max(row.date for row in valid))
    session.commit()
    return ImportReport(status="imported", rows_received=rows_received, rows_valid=len(valid),
                        inserted=inserted, updated=updated, error_count=0, errors_truncated=False, errors=[])


def _dedupe(errors: list[ImportRowError]) -> list[ImportRowError]:
    seen, unique = set(), []
    for error in errors:
        key = (error.row, error.column, error.message)
        if key not in seen:
            seen.add(key)
            unique.append(error)
    return unique


def _upsert(session: Session, rows: list[_ValidRow]) -> tuple[int, int]:
    """Insert-or-update every row; returns (inserted, updated). Caller commits."""
    key_columns = (DailySales.date, DailySales.product_id, DailySales.region_id, DailySales.channel)
    keys = [(r.date, r.product_id, r.region_id, r.channel) for r in rows]
    existing = 0
    for start in range(0, len(keys), KEY_LOOKUP_CHUNK):
        chunk = keys[start:start + KEY_LOOKUP_CHUNK]
        existing += len(session.execute(
            select(*key_columns).where(tuple_(*key_columns).in_(chunk))).all())

    dialect = session.get_bind().dialect.name
    insert_fn = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}[dialect]
    stmt = insert_fn(DailySales)
    stmt = stmt.on_conflict_do_update(
        index_elements=["date", "product_id", "region_id", "channel"],
        set_={
            "units": stmt.excluded.units,
            "revenue_minor": stmt.excluded.revenue_minor,
            "order_count": None,
            "source": SalesSource.IMPORT,
        },
    )
    payload = [
        {"date": r.date, "product_id": r.product_id, "region_id": r.region_id, "channel": r.channel,
         "units": r.units, "revenue_minor": r.revenue_minor, "order_count": None, "source": SalesSource.IMPORT}
        for r in rows
    ]
    for start in range(0, len(payload), UPSERT_CHUNK):
        session.execute(stmt, payload[start:start + UPSERT_CHUNK])
    return len(rows) - existing, existing
