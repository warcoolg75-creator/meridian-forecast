"""The weekly history every model is trained on, and the only way a model sees it.

`SalesHistory.until(i)` keeps weeks 0..i and drops everything after: the backtest hands
each model the history cut at its origin, so a model cannot read a later week because
the later weeks are not in the object it receives. tests/test_forecast_leakage.py checks
that scrambling every week after an origin changes nothing at that origin.
"""

from dataclasses import dataclass, replace
from datetime import date, timedelta

import numpy as np
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.forecasting.calendar import Calendar, festival_key, monday
from app.models import CalendarEvent, DailySales, EventType, Product, WeeklySales


@dataclass(frozen=True)
class Sku:
    index: int
    product_id: int
    sku: str
    name: str
    category: str
    launched_on: date


@dataclass(frozen=True)
class SalesHistory:
    """Complete Monday weeks, oldest first. units[s, t] is NaN before SKU s's launch week."""

    weeks: tuple[date, ...]
    units: np.ndarray
    skus: tuple[Sku, ...]
    calendar: Calendar
    data_end: date  # the last day with sales data (may fall mid-week)

    @property
    def last(self) -> int:
        return len(self.weeks) - 1

    def index(self, week: date) -> int:
        return self.weeks.index(week)

    def until(self, last_week: int) -> "SalesHistory":
        """Weeks 0..last_week only: what a model may see at an origin after that week."""
        units = self.units[:, : last_week + 1].copy()
        units.setflags(write=False)
        return replace(self, weeks=self.weeks[: last_week + 1], units=units)

    def future_weeks(self, horizon: int) -> list[date]:
        return [self.weeks[-1] + timedelta(weeks=h) for h in range(1, horizon + 1)]

    def launch_index(self, s: int) -> int:
        """First week with data for SKU s (its launch week, or 0)."""
        valid = np.flatnonzero(~np.isnan(self.units[s]))
        return int(valid[0]) if valid.size else len(self.weeks)

    def weeks_since_launch(self, s: int) -> int:
        """Weeks of data the SKU has in this history (the launch week counts)."""
        return len(self.weeks) - self.launch_index(s)


def last_complete_week(data_end: date) -> date:
    """Monday of the last Monday-Sunday week wholly inside the data."""
    start = monday(data_end)
    return start if data_end.weekday() == 6 else start - timedelta(weeks=1)


def load_history(session: Session) -> SalesHistory:
    """Units per SKU per complete week from weekly_sales, plus the calendar."""
    data_end = session.scalar(sa.select(sa.func.max(DailySales.date)))
    if data_end is None:
        raise ValueError("No sales data: run make seed first")
    last_week = last_complete_week(data_end)
    rows = session.execute(
        sa.select(WeeklySales.product_id, WeeklySales.period_start, sa.func.sum(WeeklySales.units))
        .where(WeeklySales.period_start <= last_week)
        .group_by(WeeklySales.product_id, WeeklySales.period_start)
    ).all()
    sold = {product_id for product_id, _, _ in rows}
    products = [p for p in session.scalars(sa.select(Product).order_by(Product.sku)) if p.id in sold]
    first_week = min(week for _, week, _ in rows)
    weeks = tuple(first_week + timedelta(weeks=k) for k in range((last_week - first_week).days // 7 + 1))
    position = {w: i for i, w in enumerate(weeks)}
    row_of = {p.id: i for i, p in enumerate(products)}
    units = np.zeros((len(products), len(weeks)))
    for product_id, week, total in rows:
        units[row_of[product_id], position[week]] = total
    for i, p in enumerate(products):
        before_launch = [k for k, w in enumerate(weeks) if w < monday(p.launched_on)]
        units[i, before_launch] = np.nan
    units.setflags(write=False)

    festivals: list[tuple[date, str]] = []
    promotions: dict[str, list[tuple[date, date]]] = {}
    sku_of = {p.id: p.sku for p in products}
    events = session.scalars(sa.select(CalendarEvent).order_by(CalendarEvent.date, CalendarEvent.name)).all()
    for event in events:
        if event.event_type in (EventType.PUBLIC_HOLIDAY, EventType.FESTIVAL):
            key = festival_key(event.name, event.event_type == EventType.PUBLIC_HOLIDAY)
            if key:
                festivals.append((event.date, key))
        elif event.event_type == EventType.PROMOTION and event.product_id in sku_of:
            promotions.setdefault(sku_of[event.product_id], []).append((event.date, event.end_date))

    return SalesHistory(
        weeks=weeks,
        units=units,
        skus=tuple(Sku(i, p.id, p.sku, p.name, p.category, p.launched_on) for i, p in enumerate(products)),
        calendar=Calendar(tuple(festivals), {k: tuple(v) for k, v in sorted(promotions.items())}),
        data_end=data_end,
    )
