"""The analytics queries. Every sum happens in the database, one statement per question.

Each statement reads the period (window 0) and the comparison period (window 1) together
through app/services/sales_source.py: whole weeks from weekly_sales, edge days from
daily_sales. Python only divides (shares, growth), ranks and classifies the results.

Gross margin = revenue - units x the product's unit cost: (price actually paid - unit
cost) x units, so discounts count. The schema keeps only today's unit cost, so past
periods are costed at today's cost (a known limitation, CLAUDE.md).
"""

from datetime import date, timedelta

from sqlalchemy import BigInteger, ColumnElement, case, cast, exists, func, select
from sqlalchemy.orm import Session, aliased

from app.models import Product, Region, RegionLevel, SalesOrder, SalesOrderLine, WeeklySales
from app.schemas.analytics import (
    BaselineHistory,
    ChannelRow,
    ChannelsResponse,
    Changes,
    Classification,
    PeriodInfo,
    ProductRow,
    ProductSort,
    ProductsResponse,
    RegionRow,
    RegionsResponse,
    SortOrder,
    SummaryResponse,
    TimeseriesPoint,
    TimeseriesResponse,
    Totals,
)
from app.services.analytics import classify
from app.services.analytics.events import moving_events
from app.services.analytics.scope import Scope
from app.services.bucketing import Granularity, period_end, period_start, period_start_expr, shift_days
from app.services.errors import NotFoundError
from app.services.sales_source import (
    Window,
    apply_row_filter,
    days_with_data,
    sales_row_selects,
    sales_rows,
    shifted_row_selects,
    union_rows,
)

CURRENT, BASELINE = 0, 1


class InvalidParameterError(ValueError):
    pass


# --------------------------------------------------------------------------- helpers


def _sum(expr: ColumnElement) -> ColumnElement[int]:
    # Casts keep sums integral on PostgreSQL, where SUM(bigint) returns numeric.
    return cast(func.coalesce(func.sum(expr), 0), BigInteger)


def _measures(rows, window: int, with_cost: bool) -> list[ColumnElement[int]]:
    """units, revenue (and cost) summed over one window's rows."""
    in_window = rows.c.window == window
    measures = [
        _sum(case((in_window, rows.c.units), else_=0)),
        _sum(case((in_window, rows.c.revenue_minor), else_=0)),
    ]
    if with_cost:
        cost = cast(rows.c.units, BigInteger) * Product.unit_cost_minor
        measures.append(_sum(case((in_window, cost), else_=0)))
    return measures


def _totals_rows(session: Session, scope: Scope, *group_by: ColumnElement, with_cost: bool = True,
                 rows=None, where: tuple = (), joins: tuple = ()):
    rows = rows if rows is not None else sales_rows([scope.period, scope.comparison], Granularity.WEEK,
                                                    scope.row_filter)
    source = rows.join(Product, Product.id == rows.c.product_id) if with_cost else rows
    for target, condition in joins:
        source = source.join(target, condition)
    stmt = select(*group_by, *_measures(rows, CURRENT, with_cost), *_measures(rows, BASELINE, with_cost))
    stmt = stmt.select_from(source).where(*where)
    if group_by:
        stmt = stmt.group_by(*group_by)
    return session.execute(stmt).all()


def _change(current: float | None, baseline: float | None, complete: bool) -> float | None:
    if not complete or current is None or baseline is None or baseline <= 0:
        return None
    return (current - baseline) / baseline


def _share(value: int, total: int) -> float:
    return value / total if total > 0 else 0.0


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _totals(units: int, revenue: int, cost: int, orders: int) -> Totals:
    margin = revenue - cost
    return Totals(
        revenue_minor=revenue,
        units=units,
        orders=orders,
        gross_margin_minor=margin,
        average_selling_price_minor=round(revenue / units) if units else None,
        margin_rate=margin / revenue if revenue else None,
    )


# --------------------------------------------------------------------------- summary


def _order_counts(session: Session, scope: Scope) -> tuple[int, int]:
    """Distinct orders in each window. Not daily_sales.order_count: that counts an order
    once per product line on it (350,104 lines vs 223,271 orders in the pinned data).

    Each sales_orders row is one order, and the SKU filter is an EXISTS (it never repeats
    a row), so counting rows counts distinct orders without COUNT(DISTINCT)'s hashing."""
    f = scope.row_filter

    def count(window: Window):
        # One range count per window: without region or channel filters it is answered
        # from the order_date index alone.
        stmt = select(func.count()).select_from(SalesOrder).where(
            SalesOrder.order_date.between(window.date_from, window.date_to))
        if f.region_ids is not None:
            stmt = stmt.where(SalesOrder.region_id.in_(sorted(f.region_ids)))
        if f.channels is not None:
            stmt = stmt.where(SalesOrder.channel.in_(sorted(f.channels)))
        if f.product_ids is not None:
            stmt = stmt.where(exists().where(SalesOrderLine.sales_order_id == SalesOrder.id,
                                             SalesOrderLine.product_id.in_(sorted(f.product_ids))))
        return stmt.scalar_subquery()

    current, baseline = session.execute(select(count(scope.period), count(scope.comparison))).one()
    return current, baseline


def summary(session: Session, scope: Scope) -> SummaryResponse:
    units, revenue, cost, b_units, b_revenue, b_cost = _totals_rows(session, scope)[0]
    orders, b_orders = _order_counts(session, scope)
    current = _totals(units, revenue, cost, orders)
    baseline = _totals(b_units, b_revenue, b_cost, b_orders)
    complete = scope.comparison_complete
    return SummaryResponse(
        period=scope.period_info(),
        comparison=scope.comparison_info(),
        current=current,
        baseline=baseline,
        change=Changes(
            revenue=_change(current.revenue_minor, baseline.revenue_minor, complete),
            units=_change(current.units, baseline.units, complete),
            orders=_change(current.orders, baseline.orders, complete),
            gross_margin=_change(current.gross_margin_minor, baseline.gross_margin_minor, complete),
            average_selling_price=_change(current.average_selling_price_minor,
                                          baseline.average_selling_price_minor, complete),
        ),
    )


# --------------------------------------------------------------------------- timeseries


def _bucket_starts(window: Window, granularity: Granularity) -> list[date]:
    starts, start = [], period_start(window.date_from, granularity)
    while start <= window.date_to:
        starts.append(start)
        start = period_end(start, granularity) + timedelta(days=1)
    return starts


def timeseries(session: Session, scope: Scope) -> TimeseriesResponse:
    """Each bucket of the period, with the same days `shift` earlier in the same bucket.

    The comparison reads whole weeks from weekly_sales wherever a shifted week stays inside
    one bucket, and days elsewhere (shifted_row_selects), so each comparison day lands in
    exactly the bucket its shifted date belongs to."""
    g = scope.granularity
    rows = union_rows(
        sales_row_selects([scope.period], g, scope.row_filter, first_index=CURRENT)
        + shifted_row_selects(scope.comparison, scope.shift, g, scope.row_filter, index=BASELINE)
    )
    # Sum per (window, date) first, then shift and bucket those few hundred rows: the date
    # arithmetic is string functions on SQLite, too slow to run once per cell row.
    per_day = (
        select(rows.c.window, rows.c.d, _sum(rows.c.units).label("units"),
               _sum(rows.c.revenue_minor).label("revenue_minor"))
        .group_by(rows.c.window, rows.c.d)
        .subquery("per_day")
    )
    aligned = case((per_day.c.window == CURRENT, per_day.c.d), else_=shift_days(per_day.c.d, scope.shift))
    bucket = period_start_expr(aligned, g).label("bucket")
    stmt = select(bucket, *_measures(per_day, CURRENT, False), *_measures(per_day, BASELINE, False)).group_by(bucket)
    found = {_as_date(row.bucket): row for row in session.execute(stmt)}
    history = _baseline_history(session, scope)
    baseline_bounds = (history.first_date, scope.bounds[1]) if history and scope.bounds else None

    points = []
    for start in _bucket_starts(scope.period, g):
        end = period_end(start, g)
        days = Window(max(start, scope.period.date_from), min(end, scope.period.date_to))
        covered = days_with_data(days, scope.bounds)
        row = found.get(start)
        points.append(TimeseriesPoint(
            period_start=start,
            period_end=end,
            days_covered=covered,
            is_partial=covered < (end - start).days + 1,
            units=row[1] if row else 0,
            revenue_minor=row[2] if row else 0,
            baseline_units=row[3] if row else 0,
            baseline_revenue_minor=row[4] if row else 0,
            baseline_days_covered=days_with_data(days.shifted(scope.shift), baseline_bounds),
        ))
    return TimeseriesResponse(
        period=scope.period_info(),
        comparison=scope.comparison_info(),
        granularity=g,
        points=points,
        baseline_history=history,
        moving_events=moving_events(session, scope),
    )


def _baseline_history(session: Session, scope: Scope) -> BaselineHistory | None:
    """The first day a comparison can draw on: the data's first day or, filtered to
    products, their earliest launch if later. Before a product launched there is nothing
    to compare with, which is not the same as selling nothing."""
    if not scope.bounds:
        return None
    first = scope.bounds[0]
    ids = scope.row_filter.product_ids
    if ids:
        launched = session.scalar(select(func.min(Product.launched_on)).where(Product.id.in_(sorted(ids))))
        if launched and launched > first:
            return BaselineHistory(first_date=launched, starts_with="launch")
    return BaselineHistory(first_date=first, starts_with="data")


# --------------------------------------------------------------------------- products

_SORT_KEYS = {
    ProductSort.RANK: lambda r: r.rank,
    ProductSort.SKU: lambda r: r.sku,
    ProductSort.NAME: lambda r: r.name.lower(),
    ProductSort.CATEGORY: lambda r: (r.category.lower(), r.rank),
    ProductSort.REVENUE: lambda r: r.revenue_minor,
    ProductSort.UNITS: lambda r: r.units,
    ProductSort.MARGIN: lambda r: r.gross_margin_minor,
    ProductSort.SHARE: lambda r: r.share,
    ProductSort.GROWTH: lambda r: r.growth,
    ProductSort.ABC: lambda r: r.abc,
    ProductSort.XYZ: lambda r: r.xyz,
}


def _sorted(rows: list[ProductRow], sort: ProductSort, order: SortOrder) -> list[ProductRow]:
    """Sorted on the server; rows without a value (no growth, no class) always last."""
    key = _SORT_KEYS[sort]
    present = [r for r in rows if key(r) is not None]
    missing = [r for r in rows if key(r) is None]
    present.sort(key=lambda r: (key(r), r.rank), reverse=order is SortOrder.DESC)
    return present + sorted(missing, key=lambda r: r.rank)


def products(session: Session, scope: Scope, sort: ProductSort = ProductSort.RANK,
             order: SortOrder = SortOrder.ASC) -> ProductsResponse:
    f = scope.row_filter
    catalogue = session.scalars(
        select(Product).where(Product.id.in_(sorted(f.product_ids))) if f.product_ids is not None
        else select(Product)
    ).all()
    rows_source = sales_rows([scope.period, scope.comparison], Granularity.WEEK, f)
    totals = {row[0]: row[1:] for row in _totals_rows(session, scope, rows_source.c.product_id, rows=rows_source)}
    listed = [p for p in catalogue if p.is_active or p.id in totals]

    weeks = classify.xyz_weeks(scope.period.date_to, *scope.bounds) if scope.bounds else []
    weekly: dict[tuple[int, date], int] = {}
    if weeks:
        stmt = (
            select(WeeklySales.product_id, WeeklySales.period_start, _sum(WeeklySales.units))
            .where(WeeklySales.period_start.between(weeks[0], weeks[-1]))
            .group_by(WeeklySales.product_id, WeeklySales.period_start)
        )
        for product_id, monday, units in session.execute(apply_row_filter(stmt, WeeklySales, f)):
            weekly[(product_id, _as_date(monday))] = units

    revenue = {p.sku: totals.get(p.id, (0, 0, 0, 0, 0, 0))[1] for p in listed}
    abc = classify.abc_classes(revenue)
    total_revenue = sum(revenue.values())
    ranking = {sku: i for i, sku in enumerate(sorted(revenue, key=lambda s: (-revenue[s], s)), start=1)}
    complete = scope.comparison_complete

    rows = []
    for p in listed:
        units, rev, cost, _b_units, b_rev, _b_cost = totals.get(p.id, (0, 0, 0, 0, 0, 0))
        launched = classify.weeks_since_launch(weeks, p.launched_on)
        series = [weekly.get((p.id, w), 0) for w in launched]
        cv = classify.coefficient_of_variation(series)
        rows.append(ProductRow(
            rank=ranking[p.sku],
            sku=p.sku,
            name=p.name,
            category=p.category,
            revenue_minor=rev,
            units=units,
            gross_margin_minor=rev - cost,
            share=_share(rev, total_revenue),
            baseline_revenue_minor=b_rev,
            growth=_change(rev, b_rev, complete),
            abc=abc[p.sku],
            xyz=classify.xyz_class(cv),
            xyz_cv=round(cv, 4) if cv is not None else None,
            xyz_weeks=len(series),
            sparkline=[weekly.get((p.id, w), 0) for w in weeks[-classify.SPARKLINE_WEEKS:]],
        ))

    xyz_window = (PeriodInfo(date_from=weeks[0], date_to=weeks[-1] + timedelta(days=6), days=len(weeks) * 7,
                             days_with_data=len(weeks) * 7) if weeks else scope.period_info())
    return ProductsResponse(
        period=scope.period_info(),
        comparison=scope.comparison_info(),
        classification=Classification(
            abc_a_share=classify.ABC_A_SHARE,
            abc_b_share=classify.ABC_B_SHARE,
            xyz_x_below=classify.XYZ_X_BELOW,
            xyz_y_up_to=classify.XYZ_Y_UP_TO,
            xyz_window=xyz_window,
            xyz_min_weeks=classify.XYZ_MIN_WEEKS,
        ),
        sort=sort,
        order=order,
        rows=_sorted(rows, sort, order),
    )


# --------------------------------------------------------------------------- regions


def regions(session: Session, scope: Scope, level: RegionLevel = RegionLevel.STATE,
            parent_code: str | None = None) -> RegionsResponse:
    """Totals per state (a state's row includes its cities) or per city, optionally only
    the cities of one parent (the drill-down)."""
    if level is RegionLevel.COUNTRY:
        raise InvalidParameterError("level must be state or city")
    if parent_code is not None and level is not RegionLevel.CITY:
        raise InvalidParameterError("parent only applies to level=city")
    parent_id = None
    if parent_code is not None:
        parent_id = session.scalar(select(Region.id).where(Region.code == parent_code))
        if parent_id is None:
            raise NotFoundError(f"Unknown region code: {parent_code}")

    rows = sales_rows([scope.period, scope.comparison], Granularity.WEEK, scope.row_filter)
    sale_region = aliased(Region)
    if level is RegionLevel.STATE:
        key = case((sale_region.level == RegionLevel.STATE.value, sale_region.id),
                   else_=sale_region.parent_region_id)
        where = (sale_region.level != RegionLevel.COUNTRY.value,)
    else:
        key = sale_region.id
        where = (sale_region.level == RegionLevel.CITY.value,)
        if parent_id is not None:
            where += (sale_region.parent_region_id == parent_id,)
    results = _totals_rows(session, scope, key.label("region_id"), with_cost=False, rows=rows, where=where,
                           joins=((sale_region, sale_region.id == rows.c.region_id),))

    parent = aliased(Region)
    info = {r.id: r for r in session.execute(
        select(Region.id, Region.code, Region.name, Region.level, parent.code.label("parent_code"))
        .outerjoin(parent, parent.id == Region.parent_region_id)
        .where(Region.id.in_([row[0] for row in results]))
    )}
    total = sum(row[2] for row in results)
    complete = scope.comparison_complete
    out = [
        RegionRow(
            code=info[region_id].code,
            name=info[region_id].name,
            level=info[region_id].level,
            parent_code=info[region_id].parent_code,
            revenue_minor=revenue,
            units=units,
            share=_share(revenue, total),
            baseline_revenue_minor=b_revenue,
            growth=_change(revenue, b_revenue, complete),
        )
        for region_id, units, revenue, _b_units, b_revenue in results
        if region_id is not None and (revenue or b_revenue)
    ]
    out.sort(key=lambda r: (-r.revenue_minor, r.code))
    return RegionsResponse(period=scope.period_info(), comparison=scope.comparison_info(), level=level,
                           parent_code=parent_code, rows=out)


# --------------------------------------------------------------------------- channels


def channels(session: Session, scope: Scope) -> ChannelsResponse:
    rows = sales_rows([scope.period, scope.comparison], Granularity.WEEK, scope.row_filter)
    results = _totals_rows(session, scope, rows.c.channel, with_cost=False, rows=rows)
    total = sum(row[2] for row in results)
    b_total = sum(row[4] for row in results)
    complete = scope.comparison_complete
    out = [
        ChannelRow(
            channel=channel,
            revenue_minor=revenue,
            units=units,
            share=_share(revenue, total),
            baseline_revenue_minor=b_revenue,
            baseline_share=_share(b_revenue, b_total) if complete and b_total else None,
            growth=_change(revenue, b_revenue, complete),
        )
        for channel, units, revenue, _b_units, b_revenue in results
        if revenue or b_revenue
    ]
    out.sort(key=lambda r: (-r.revenue_minor, r.channel.value))
    return ChannelsResponse(period=scope.period_info(), comparison=scope.comparison_info(), rows=out)
