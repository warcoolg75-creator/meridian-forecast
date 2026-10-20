"""Calendar events for analytics: what touches a product, and which festivals moved.

Same period last year compares the same weekdays 52 weeks apart, but lunar festivals do
not keep their date: Diwali fell on 12 Nov 2023, 31 Oct 2024 and 20 Oct 2025. A
festival in one period and a different place (or not at all) in the other swings the
year-over-year comparison without any change in demand. moving_events() names them so
the chart can say so.
"""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import CalendarEvent, EventType, LineCapability, Plant, Product, ProductionLine, Region
from app.schemas.analytics import ComparisonMode, MovingEvent, ProductEvent
from app.services.sales_source import Window

HOLIDAY_TYPES = (EventType.PUBLIC_HOLIDAY, EventType.FESTIVAL)
# A festival counts as moved when its two dates sit more than this far apart once the
# comparison is shifted. Fixed-date holidays shift by 1-2 days under a 364-day shift.
MOVED_MORE_THAN_DAYS = 3
# Occurrences further apart than this are different years' festivals, not a pair.
PAIR_WITHIN_DAYS = 45


def product_events(session: Session, product: Product, window: Window) -> list[ProductEvent]:
    """Events overlapping the window that touch this product: its promotions, every
    holiday and festival (national or regional), and shutdowns of plants with a line
    that makes it."""
    plant_ids = select(ProductionLine.plant_id).join(
        LineCapability, LineCapability.production_line_id == ProductionLine.id
    ).where(LineCapability.product_id == product.id)
    stmt = (
        select(CalendarEvent, Region.code, Plant.code)
        .outerjoin(Region, Region.id == CalendarEvent.region_id)
        .outerjoin(Plant, Plant.id == CalendarEvent.plant_id)
        .where(CalendarEvent.date <= window.date_to, CalendarEvent.end_date >= window.date_from)
        .where(or_(
            and_(CalendarEvent.event_type == EventType.PROMOTION, CalendarEvent.product_id == product.id),
            CalendarEvent.event_type.in_(HOLIDAY_TYPES),
            and_(CalendarEvent.event_type == EventType.PLANT_SHUTDOWN, CalendarEvent.plant_id.in_(plant_ids)),
        ))
        .order_by(CalendarEvent.date, CalendarEvent.name)
    )
    events = []
    for event, region_code, plant_code in session.execute(stmt):
        if event.event_type is EventType.PROMOTION:
            scope = "product"
        elif event.event_type is EventType.PLANT_SHUTDOWN:
            scope = "plant"
        else:
            scope = "regional" if event.region_id else "national"
        events.append(ProductEvent(
            date=event.date, end_date=event.end_date, name=event.name, event_type=event.event_type,
            scope=scope, region_code=region_code, plant_code=plant_code, impact_note=event.impact_note,
        ))
    return events


def _region_scope(session: Session, region_ids: frozenset[int] | None) -> set[int] | None:
    """The filtered regions and their ancestors: a Maharashtra festival applies to a
    Mumbai-only view. None = no region filter, every region applies."""
    if region_ids is None:
        return None
    parents = dict(session.execute(select(Region.id, Region.parent_region_id)).all())
    scope = set()
    for region_id in region_ids:
        while region_id is not None and region_id not in scope:
            scope.add(region_id)
            region_id = parents.get(region_id)
    return scope


def _base_name(name: str) -> str:
    """'Id-ul-Fitr (estimated)' and 'Id-ul-Fitr' are the same festival."""
    return name.removesuffix(" (estimated)")


def moving_events(session, scope) -> list[MovingEvent]:
    """Holidays and festivals whose date in the period and in the comparison period
    differ by more than MOVED_MORE_THAN_DAYS once aligned, or that fall in only one of
    them. Only for same_period_last_year: a previous period is a different season."""
    if scope.params.comparison is not ComparisonMode.SAME_PERIOD_LAST_YEAR:
        return []
    period, comparison, shift = scope.period, scope.comparison, timedelta(days=scope.shift)
    stmt = (
        select(CalendarEvent.name, CalendarEvent.date, CalendarEvent.region_id, Region.code)
        .outerjoin(Region, Region.id == CalendarEvent.region_id)
        .where(CalendarEvent.event_type.in_(HOLIDAY_TYPES))
        .where(or_(CalendarEvent.date.between(period.date_from, period.date_to),
                   CalendarEvent.date.between(comparison.date_from, comparison.date_to)))
    )
    regions = _region_scope(session, scope.row_filter.region_ids)
    if regions is not None:
        stmt = stmt.where(or_(CalendarEvent.region_id.is_(None), CalendarEvent.region_id.in_(sorted(regions))))

    occurrences: dict[tuple[str, str | None], dict[str, list[date]]] = defaultdict(
        lambda: {"current": [], "comparison": []})
    for name, day, _region_id, region_code in session.execute(stmt):
        key = (_base_name(name), region_code)
        if period.date_from <= day <= period.date_to:
            occurrences[key]["current"].append(day)
        if comparison.date_from <= day <= comparison.date_to:
            occurrences[key]["comparison"].append(day)

    moved: list[MovingEvent] = []
    for (name, region_code), days in occurrences.items():
        unpaired = sorted(days["comparison"])
        for current in sorted(days["current"]):
            nearest = min(unpaired, key=lambda d: abs((current - (d + shift)).days), default=None)
            if nearest is not None and abs((current - (nearest + shift)).days) <= PAIR_WITHIN_DAYS:
                unpaired.remove(nearest)
                apart = (current - (nearest + shift)).days
                if abs(apart) > MOVED_MORE_THAN_DAYS:
                    moved.append(MovingEvent(name=name, region_code=region_code, current_date=current,
                                             comparison_date=nearest, aligned_date=nearest + shift,
                                             days_apart=apart))
            else:
                moved.append(MovingEvent(name=name, region_code=region_code, current_date=current,
                                         comparison_date=None, aligned_date=None, days_apart=None))
        for leftover in unpaired:
            moved.append(MovingEvent(name=name, region_code=region_code, current_date=None,
                                     comparison_date=leftover, aligned_date=leftover + shift, days_apart=None))
    moved.sort(key=lambda e: (e.current_date or e.aligned_date, e.name))
    return moved
