"""The request's filters, resolved once: windows, comparison, ids."""

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Channel
from app.schemas.analytics import ComparisonInfo, ComparisonMode, PeriodInfo
from app.services.bucketing import Granularity
from app.services.sales_query import row_filter_for
from app.services.sales_source import RowFilter, Window, data_bounds, days_with_data

# Same period last year = 52 weeks back: the data has a day-of-week profile, and a
# 364-day shift keeps Mondays on Mondays. Festivals still move; see moving_events().
YEAR_SHIFT_DAYS = 364
# With no date_from, the period is the 13 weeks ending on date_to.
DEFAULT_DAYS = 91


class InvalidRangeError(ValueError):
    pass


@dataclass(frozen=True)
class AnalyticsParams:
    date_from: date | None = None
    date_to: date | None = None
    skus: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()
    channels: tuple[Channel, ...] = ()
    granularity: Granularity = Granularity.WEEK
    comparison: ComparisonMode = ComparisonMode.SAME_PERIOD_LAST_YEAR


@dataclass(frozen=True)
class Scope:
    params: AnalyticsParams
    bounds: tuple[date, date] | None
    period: Window
    comparison: Window
    shift: int
    row_filter: RowFilter = field(default_factory=RowFilter)

    @property
    def granularity(self) -> Granularity:
        return self.params.granularity

    @property
    def comparison_complete(self) -> bool:
        return days_with_data(self.comparison, self.bounds) == self.comparison.days

    def period_info(self) -> PeriodInfo:
        return PeriodInfo(date_from=self.period.date_from, date_to=self.period.date_to, days=self.period.days,
                          days_with_data=days_with_data(self.period, self.bounds))

    def comparison_info(self) -> ComparisonInfo:
        return ComparisonInfo(
            date_from=self.comparison.date_from, date_to=self.comparison.date_to, days=self.comparison.days,
            days_with_data=days_with_data(self.comparison, self.bounds), mode=self.params.comparison,
            shift_days=self.shift, complete=self.comparison_complete,
        )


def resolve_scope(session: Session, params: AnalyticsParams) -> Scope:
    """Defaults: date_to = the last day with data, date_from = 13 weeks before it. A
    range reaching past the stored history is clipped to it, so a comparison never sets
    a partial period against a full one."""
    if params.date_from and params.date_to and params.date_from > params.date_to:
        raise InvalidRangeError("date_from must be on or before date_to")
    bounds = data_bounds(session)
    date_to = params.date_to or (bounds[1] if bounds else date.today())
    date_from = params.date_from or date_to - timedelta(days=DEFAULT_DAYS - 1)
    if date_from > date_to:
        raise InvalidRangeError("date_from must be on or before date_to")
    period = Window(date_from, date_to)
    if bounds:
        clipped = Window(max(date_from, bounds[0]), min(date_to, bounds[1]))
        if clipped.date_from <= clipped.date_to:
            period = clipped
    shift = YEAR_SHIFT_DAYS if params.comparison is ComparisonMode.SAME_PERIOD_LAST_YEAR else period.days
    return Scope(
        params=params,
        bounds=bounds,
        period=period,
        comparison=period.shifted(shift),
        shift=shift,
        row_filter=row_filter_for(session, list(params.skus), list(params.regions), list(params.channels)),
    )
