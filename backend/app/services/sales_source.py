"""Where sales rows are read from: whole periods from the rollups, edges from daily_sales.

weekly_sales and monthly_sales hold daily_sales summed per week and per month (see
app/services/rollup.py). A date range rarely starts on a Monday or a 1st, so a range is
split into the whole periods inside it, read from the rollup, and the days at either
edge, read from daily_sales. The union carries the same columns either way:

    d            the row's date: the period start for rollup rows, the day for daily rows
    product_id, region_id, channel, units, revenue_minor, order_count
    window       which requested window the row belongs to (0 = current, 1 = comparison)

Bucketing d by the same or a coarser granularity than its source gives exactly what
bucketing daily_sales would (tests/test_sales_source.py checks it), at a fraction of the
rows: 36,613 weekly rows instead of 207,981 daily ones for the pinned dataset.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import Select, Subquery, func, literal, select, union_all
from sqlalchemy.orm import Session

from app.models import Channel, DailySales, MonthlySales, WeeklySales
from app.services.bucketing import Granularity, period_end, period_start

ONE_DAY = timedelta(days=1)

ROLLUPS = {Granularity.WEEK: WeeklySales, Granularity.MONTH: MonthlySales}


@dataclass(frozen=True)
class Window:
    """An inclusive date range."""

    date_from: date
    date_to: date

    @property
    def days(self) -> int:
        return (self.date_to - self.date_from).days + 1

    def shifted(self, days: int) -> "Window":
        return Window(self.date_from - timedelta(days=days), self.date_to - timedelta(days=days))


@dataclass(frozen=True)
class RowFilter:
    """Resolved filters: ids, not codes. None means "no filter on this dimension"."""

    product_ids: frozenset[int] | None = None
    region_ids: frozenset[int] | None = None
    channels: frozenset[Channel] | None = None


@dataclass(frozen=True)
class PeriodPlan:
    """A window split into whole periods (first and last period starts) and edge days."""

    whole: tuple[date, date] | None
    edges: tuple[Window, ...]


def plan_periods(window: Window, granularity: Granularity) -> PeriodPlan:
    """Split a window into the whole periods inside it and the leftover days at its edges."""
    if granularity is Granularity.DAY:
        return PeriodPlan(whole=None, edges=(window,))
    first = window.date_from
    if period_start(first, granularity) != first:
        first = period_end(period_start(first, granularity), granularity) + ONE_DAY
    last_end = window.date_to
    if period_end(period_start(last_end, granularity), granularity) != last_end:
        last_end = period_start(last_end, granularity) - ONE_DAY
    if first > last_end:
        return PeriodPlan(whole=None, edges=(window,))
    edges = []
    if window.date_from < first:
        edges.append(Window(window.date_from, first - ONE_DAY))
    if window.date_to > last_end:
        edges.append(Window(last_end + ONE_DAY, window.date_to))
    return PeriodPlan(whole=(first, period_start(last_end, granularity)), edges=tuple(edges))


def apply_row_filter(stmt: Select, model, row_filter: RowFilter) -> Select:
    if row_filter.product_ids is not None:
        stmt = stmt.where(model.product_id.in_(sorted(row_filter.product_ids)))
    if row_filter.region_ids is not None:
        stmt = stmt.where(model.region_id.in_(sorted(row_filter.region_ids)))
    if row_filter.channels is not None:
        stmt = stmt.where(model.channel.in_(sorted(row_filter.channels)))
    return stmt


def _part(model, date_column, lo: date, hi: date, row_filter: RowFilter, window_index: int) -> Select:
    stmt = select(
        date_column.label("d"),
        model.product_id,
        model.region_id,
        model.channel,
        model.units,
        model.revenue_minor,
        model.order_count,
        literal(window_index).label("window"),
    ).where(date_column >= lo, date_column <= hi)
    return apply_row_filter(stmt, model, row_filter)


def sales_row_selects(windows: list[Window], granularity: Granularity, row_filter: RowFilter,
                      first_index: int = 0) -> list[Select]:
    """SELECTs covering each window, read at `granularity` where whole periods allow it;
    window i is tagged first_index + i."""
    parts = []
    rollup = ROLLUPS.get(granularity)
    for index, window in enumerate(windows, start=first_index):
        plan = plan_periods(window, granularity)
        if plan.whole and rollup is not None:
            parts.append(_part(rollup, rollup.period_start, plan.whole[0], plan.whole[1], row_filter, index))
        for edge in plan.edges:
            parts.append(_part(DailySales, DailySales.date, edge.date_from, edge.date_to, row_filter, index))
    return parts


def shifted_row_selects(window: Window, shift: int, granularity: Granularity, row_filter: RowFilter,
                        index: int) -> list[Select]:
    """Rows covering `window` such that every row's days, moved `shift` days later, fall in
    one `granularity` bucket: so bucketing (d + shift) is exact for weekly rows too.

    A comparison window 364 days back keeps Mondays on Mondays, so whole weeks map onto
    whole weeks; for month buckets a shifted week can straddle two months, and only those
    weeks (and the window's edges) are read day by day. With a shift that is not whole
    weeks, everything is daily."""
    if granularity is Granularity.DAY or shift % 7 != 0:
        return sales_row_selects([window], Granularity.DAY, row_filter, first_index=index)
    if granularity is Granularity.WEEK:
        return sales_row_selects([window], Granularity.WEEK, row_filter, first_index=index)
    offset = timedelta(days=shift)
    plan = plan_periods(window, Granularity.WEEK)
    week_ranges: list[tuple[date, date]] = []
    day_ranges: list[Window] = list(plan.edges)
    if plan.whole:
        monday = plan.whole[0]
        while monday <= plan.whole[1]:
            sunday = monday + timedelta(days=6)
            if period_start(monday + offset, granularity) == period_start(sunday + offset, granularity):
                if week_ranges and week_ranges[-1][1] == monday - timedelta(days=7):
                    week_ranges[-1] = (week_ranges[-1][0], monday)
                else:
                    week_ranges.append((monday, monday))
            else:
                day_ranges.append(Window(monday, sunday))
            monday += timedelta(days=7)
    parts = [_part(WeeklySales, WeeklySales.period_start, lo, hi, row_filter, index) for lo, hi in week_ranges]
    parts += [_part(DailySales, DailySales.date, w.date_from, w.date_to, row_filter, index) for w in day_ranges]
    return parts


def union_rows(parts: list[Select]) -> Subquery:
    return parts[0].subquery("sales_rows") if len(parts) == 1 else union_all(*parts).subquery("sales_rows")


def sales_rows(windows: list[Window], granularity: Granularity, row_filter: RowFilter) -> Subquery:
    """The union of rows covering each window, read at `granularity` where whole periods
    allow it. Windows may overlap (a 3-year range against last year); each row is then
    returned once per window it falls in, tagged with that window's index."""
    return union_rows(sales_row_selects(windows, granularity, row_filter))


def data_bounds(session: Session) -> tuple[date, date] | None:
    """First and last day with any sales, or None when daily_sales is empty.

    Two ordered LIMIT 1 subqueries, not MIN() and MAX() in one SELECT: SQLite answers a
    lone MIN or MAX from the index, but with both in one statement it scans every row
    (about 20-100 ms on the pinned dataset, paid by every analytics call)."""
    first = select(DailySales.date).order_by(DailySales.date).limit(1).scalar_subquery()
    last = select(DailySales.date).order_by(DailySales.date.desc()).limit(1).scalar_subquery()
    first_day, last_day = session.execute(select(first, last)).one()
    return (first_day, last_day) if first_day else None


def days_with_data(window: Window, bounds: tuple[date, date] | None) -> int:
    """How many of the window's days lie inside the stored history."""
    if bounds is None:
        return 0
    lo, hi = max(window.date_from, bounds[0]), min(window.date_to, bounds[1])
    return max(0, (hi - lo).days + 1)
