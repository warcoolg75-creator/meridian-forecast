"""GET /sales/daily: bucketed sales, paged with a keyset cursor.

Results are ordered by (period_start, product_id, region_id, channel), keeping only the
dimensions in group_by. A page is "the next `limit` rows after this key", so every page
costs the same however deep it is; OFFSET paging re-ran the whole aggregation and then
skipped rows (12.4 s for 21 pages on SQLite and about 42 s on the hosted PostgreSQL,
against 0.5 s and 3.3 s now; see CLAUDE.md, Known issues).

Day granularity with all three dimensions is the raw daily_sales row, so it pages
straight down the table's unique index. Coarser or partial groupings aggregate, reading
weeks and months from the rollups where the range allows (app/services/sales_source.py).
"""

import base64
import binascii
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from sqlalchemy import BigInteger, Select, cast, func, select, tuple_
from sqlalchemy.orm import Session

from app.models import Channel, DailySales, Product, Region
from app.schemas.sales import SalesPeriod
from app.services.bucketing import Granularity, period_end, period_start, period_start_expr
from app.services.errors import NotFoundError
from app.services.sales_source import RowFilter, Window, data_bounds, sales_rows


class GroupBy(StrEnum):
    SKU = "sku"
    REGION = "region"
    CHANNEL = "channel"


# Key order within a period: product, region, channel (ids, so no collation differences).
DIMENSION_ORDER = (GroupBy.SKU, GroupBy.REGION, GroupBy.CHANNEL)
CURSOR_VERSION = 1


class InvalidCursorError(ValueError):
    """The cursor is malformed or was issued for a different granularity or grouping."""


@dataclass(frozen=True)
class SalesQuery:
    skus: list[str] = field(default_factory=list)
    region_codes: list[str] = field(default_factory=list)
    channels: list[Channel] = field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    granularity: Granularity = Granularity.DAY
    group_by: list[GroupBy] = field(default_factory=list)


def region_ids_with_descendants(session: Session, codes: list[str]) -> set[int]:
    """Resolve region codes to ids, including every region below them in the tree."""
    rows = session.execute(select(Region.id, Region.code, Region.parent_region_id)).all()
    id_by_code = {row.code: row.id for row in rows}
    missing = sorted(set(codes) - id_by_code.keys())
    if missing:
        raise NotFoundError(f"Unknown region code(s): {', '.join(missing)}")

    children: dict[int, list[int]] = defaultdict(list)
    for row in rows:
        if row.parent_region_id is not None:
            children[row.parent_region_id].append(row.id)

    result: set[int] = set()
    stack = [id_by_code[code] for code in codes]
    while stack:
        region_id = stack.pop()
        if region_id not in result:
            result.add(region_id)
            stack.extend(children[region_id])
    return result


def product_ids_for(session: Session, skus: list[str]) -> list[int]:
    rows = session.execute(select(Product.sku, Product.id).where(Product.sku.in_(skus))).all()
    found = {row.sku: row.id for row in rows}
    missing = sorted(set(skus) - found.keys())
    if missing:
        raise NotFoundError(f"Unknown sku(s): {', '.join(missing)}")
    return list(found.values())


def row_filter_for(session: Session, skus: list[str], region_codes: list[str],
                   channels: list[Channel]) -> RowFilter:
    return RowFilter(
        product_ids=frozenset(product_ids_for(session, skus)) if skus else None,
        region_ids=frozenset(region_ids_with_descendants(session, region_codes)) if region_codes else None,
        channels=frozenset(channels) if channels else None,
    )


# --------------------------------------------------------------------------- cursor


def _dimensions(q: SalesQuery) -> list[GroupBy]:
    return [d for d in DIMENSION_ORDER if d in q.group_by]


def encode_cursor(q: SalesQuery, key: tuple) -> str:
    payload = {"v": CURSOR_VERSION, "g": q.granularity.value, "by": [d.value for d in _dimensions(q)],
               "k": [key[0].isoformat(), *key[1:]]}
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_cursor(q: SalesQuery, token: str) -> tuple:
    try:
        payload = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        if payload["v"] != CURSOR_VERSION:
            raise InvalidCursorError("Unsupported cursor version.")
        if payload["g"] != q.granularity.value or payload["by"] != [d.value for d in _dimensions(q)]:
            raise InvalidCursorError("The cursor was issued for a different granularity or group_by.")
        key = payload["k"]
        dims = _dimensions(q)
        if not isinstance(key, list) or len(key) != 1 + len(dims):
            raise InvalidCursorError("Malformed cursor.")
        values: list = [date.fromisoformat(key[0])]
        for dim, value in zip(dims, key[1:], strict=True):
            if dim is GroupBy.CHANNEL:
                values.append(Channel(value))
            elif isinstance(value, int) and not isinstance(value, bool):
                values.append(value)
            else:
                raise InvalidCursorError("Malformed cursor.")
        return tuple(values)
    except InvalidCursorError:
        raise
    except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidCursorError("Malformed cursor.") from exc


# --------------------------------------------------------------------------- query


def _raw_rows_statement(q: SalesQuery, window: Window, row_filter: RowFilter, after: tuple | None) -> Select:
    """Day granularity, all three dimensions: daily_sales rows as they are, in index order."""
    key = (DailySales.date, DailySales.product_id, DailySales.region_id, DailySales.channel)
    stmt = (
        select(
            DailySales.date.label("period_start"),
            DailySales.product_id,
            DailySales.region_id,
            DailySales.channel,
            Product.sku,
            Region.code.label("region_code"),
            DailySales.units,
            DailySales.revenue_minor,
            DailySales.order_count,
        )
        .join(Product, Product.id == DailySales.product_id)
        .join(Region, Region.id == DailySales.region_id)
        .where(DailySales.date >= window.date_from, DailySales.date <= window.date_to)
    )
    if row_filter.product_ids is not None:
        stmt = stmt.where(DailySales.product_id.in_(sorted(row_filter.product_ids)))
    if row_filter.region_ids is not None:
        stmt = stmt.where(DailySales.region_id.in_(sorted(row_filter.region_ids)))
    if row_filter.channels is not None:
        stmt = stmt.where(DailySales.channel.in_(sorted(row_filter.channels)))
    if after is not None:
        stmt = stmt.where(tuple_(*key) > tuple_(*after))
    return stmt.order_by(*key)


def _grouped_statement(q: SalesQuery, window: Window, row_filter: RowFilter, after: tuple | None) -> Select:
    # Rows before the cursor's period cannot be on this page: start reading there.
    read_from = max(window.date_from, after[0]) if after else window.date_from
    rows = sales_rows([Window(read_from, window.date_to)], q.granularity, row_filter)
    period = period_start_expr(rows.c.d, q.granularity).label("period_start")
    dims = _dimensions(q)
    columns = {GroupBy.SKU: rows.c.product_id, GroupBy.REGION: rows.c.region_id, GroupBy.CHANNEL: rows.c.channel}
    group_columns = [columns[d] for d in dims]
    grouped = (
        select(
            period,
            *group_columns,
            # Casts keep the sums integral on PostgreSQL, where SUM(bigint) returns numeric.
            cast(func.sum(rows.c.units), BigInteger).label("units"),
            cast(func.sum(rows.c.revenue_minor), BigInteger).label("revenue_minor"),
            cast(func.sum(rows.c.order_count), BigInteger).label("order_count"),
        )
        .group_by(period, *group_columns)
        .subquery("grouped")
    )
    key = [grouped.c.period_start, *[grouped.c[columns[d].name] for d in dims]]
    stmt = select(grouped)
    if GroupBy.SKU in dims:
        stmt = stmt.add_columns(Product.sku).join(Product, Product.id == grouped.c.product_id)
    if GroupBy.REGION in dims:
        stmt = stmt.add_columns(Region.code.label("region_code")).join(Region, Region.id == grouped.c.region_id)
    if after is not None:
        stmt = stmt.where(tuple_(*key) > tuple_(*after))
    return stmt.order_by(*key)


def query_sales(session: Session, q: SalesQuery, *, limit: int,
                cursor: str | None = None) -> tuple[list[SalesPeriod], str | None]:
    """One page of results and the cursor for the next one (None on the last page)."""
    after = decode_cursor(q, cursor) if cursor else None
    row_filter = row_filter_for(session, q.skus, q.region_codes, q.channels)
    bounds = data_bounds(session)
    if bounds is None:
        return [], None
    window = Window(q.date_from or bounds[0], q.date_to or bounds[1])
    if window.date_from > window.date_to:
        return [], None

    dims = _dimensions(q)
    if q.granularity is Granularity.DAY and len(dims) == len(DIMENSION_ORDER):
        stmt = _raw_rows_statement(q, window, row_filter, after)
    else:
        stmt = _grouped_statement(q, window, row_filter, after)
    rows = session.execute(stmt.limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    # A bucket is partial when the requested range or the edges of the stored history
    # cut into it, e.g. the current week when history ends yesterday.
    lower = max(d for d in (q.date_from, bounds[0]) if d is not None)
    upper = min(d for d in (q.date_to, bounds[1]) if d is not None)

    items = []
    for row in rows:
        start = row.period_start if isinstance(row.period_start, date) else date.fromisoformat(row.period_start)
        start = period_start(start, q.granularity)
        end = period_end(start, q.granularity)
        days_covered = (min(end, upper) - max(start, lower)).days + 1
        items.append(
            SalesPeriod(
                period_start=start,
                period_end=end,
                days_covered=days_covered,
                is_partial=days_covered < (end - start).days + 1,
                sku=row.sku if GroupBy.SKU in dims else None,
                region_code=row.region_code if GroupBy.REGION in dims else None,
                channel=row.channel if GroupBy.CHANNEL in dims else None,
                units=row.units,
                revenue_minor=row.revenue_minor,
                order_count=row.order_count,
            )
        )

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        key_values = {GroupBy.SKU: last.product_id if GroupBy.SKU in dims else None,
                      GroupBy.REGION: last.region_id if GroupBy.REGION in dims else None,
                      GroupBy.CHANNEL: last.channel if GroupBy.CHANNEL in dims else None}
        key = (items[-1].period_start, *[key_values[d] for d in dims])
        next_cursor = encode_cursor(q, tuple(v.value if isinstance(v, Channel) else v for v in key))
    return items, next_cursor
