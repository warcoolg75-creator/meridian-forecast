from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from sqlalchemy import BigInteger, Select, cast, func, select
from sqlalchemy.orm import Session

from app.models import Channel, DailySales, Product, Region
from app.schemas.sales import SalesPeriod
from app.services.bucketing import Granularity, period_end, period_start_expr
from app.services.errors import NotFoundError


class GroupBy(StrEnum):
    SKU = "sku"
    REGION = "region"
    CHANNEL = "channel"


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


def _product_ids(session: Session, skus: list[str]) -> list[int]:
    rows = session.execute(select(Product.sku, Product.id).where(Product.sku.in_(skus))).all()
    found = {row.sku: row.id for row in rows}
    missing = sorted(set(skus) - found.keys())
    if missing:
        raise NotFoundError(f"Unknown sku(s): {', '.join(missing)}")
    return list(found.values())


def _grouped_statement(session: Session, q: SalesQuery) -> Select:
    period = period_start_expr(DailySales.date, q.granularity).label("period_start")
    dimensions = []
    stmt = select().select_from(DailySales)
    if GroupBy.SKU in q.group_by:
        stmt = stmt.join(Product, Product.id == DailySales.product_id)
        dimensions.append(Product.sku.label("sku"))
    if GroupBy.REGION in q.group_by:
        stmt = stmt.join(Region, Region.id == DailySales.region_id)
        dimensions.append(Region.code.label("region_code"))
    if GroupBy.CHANNEL in q.group_by:
        dimensions.append(DailySales.channel.label("channel"))

    if q.skus:
        stmt = stmt.where(DailySales.product_id.in_(_product_ids(session, q.skus)))
    if q.region_codes:
        stmt = stmt.where(DailySales.region_id.in_(region_ids_with_descendants(session, q.region_codes)))
    if q.channels:
        stmt = stmt.where(DailySales.channel.in_(q.channels))
    if q.date_from:
        stmt = stmt.where(DailySales.date >= q.date_from)
    if q.date_to:
        stmt = stmt.where(DailySales.date <= q.date_to)

    # Casts keep the sums integral on PostgreSQL, where SUM(bigint) returns numeric.
    return (
        stmt.add_columns(
            period,
            *dimensions,
            cast(func.sum(DailySales.units), BigInteger).label("units"),
            cast(func.sum(DailySales.revenue_minor), BigInteger).label("revenue_minor"),
            cast(func.sum(DailySales.order_count), BigInteger).label("order_count"),
        )
        .group_by(period, *dimensions)
        .order_by(period, *dimensions)
    )


def query_sales(session: Session, q: SalesQuery, *, limit: int, offset: int) -> tuple[list[SalesPeriod], int]:
    stmt = _grouped_statement(session, q)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.execute(stmt.limit(limit).offset(offset)).all()

    # A bucket is partial when the requested range or the edges of the stored
    # history cut into it, e.g. the current week when history ends yesterday.
    data_min, data_max = session.execute(select(func.min(DailySales.date), func.max(DailySales.date))).one()
    lower = max(d for d in (q.date_from, data_min) if d is not None) if data_min else q.date_from
    upper = min(d for d in (q.date_to, data_max) if d is not None) if data_max else q.date_to

    items = []
    for row in rows:
        start = row.period_start
        end = period_end(start, q.granularity)
        covered_from = max(start, lower) if lower else start
        covered_to = min(end, upper) if upper else end
        days_covered = (covered_to - covered_from).days + 1
        items.append(
            SalesPeriod(
                period_start=start,
                period_end=end,
                days_covered=days_covered,
                is_partial=days_covered < (end - start).days + 1,
                sku=row.sku if GroupBy.SKU in q.group_by else None,
                region_code=row.region_code if GroupBy.REGION in q.group_by else None,
                channel=row.channel if GroupBy.CHANNEL in q.group_by else None,
                units=row.units,
                revenue_minor=row.revenue_minor,
                order_count=row.order_count,
            )
        )
    return items, total
