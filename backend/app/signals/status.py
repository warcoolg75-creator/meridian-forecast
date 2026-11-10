"""Row counts and gaps per series, and per news category: `make signals-status`.

A gap is an expected day with no observation, between the backfill start and the latest
stored day: every calendar day for daily weather and pageviews, Monday to Friday for the
FRED daily series (markets close at weekends; their holidays still count as gaps, which
FRED itself reports as missing), every month for monthly series. Forecast series are
listed without gaps: they only ever hold the latest forecast.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import NewsItem, NewsItemCategory, SignalFetch, SignalObservation, SignalSeries, SignalSource
from app.signals.pipeline import BACKFILL_START


@dataclass
class SeriesGaps:
    key: str
    source: str
    rows: int
    first: date | None
    last: date | None
    expected: int
    missing: int
    ranges: list[tuple[date, date]] = field(default_factory=list)
    status: str = ""


def _expected_days(series: SignalSeries, start: date, end: date) -> list[date]:
    if series.frequency.value == "monthly":
        out, cursor = [], start.replace(day=1)
        if cursor < start:
            cursor = (cursor + timedelta(days=32)).replace(day=1)
        while cursor <= end:
            out.append(cursor)
            cursor = (cursor + timedelta(days=32)).replace(day=1)
        return out
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    if series.source_code == "fred":  # trading / business days only
        days = [d for d in days if d.weekday() < 5]
    return days


def _ranges(missing: list[date], step_ok) -> list[tuple[date, date]]:
    out: list[list[date]] = []
    for day in missing:
        if out and step_ok(out[-1][1], day):
            out[-1][1] = day
        else:
            out.append([day, day])
    return sorted(((a, b) for a, b in out), key=lambda r: (r[0] - r[1]).days)


def series_gaps(session: Session) -> list[SeriesGaps]:
    sources = {s.id: s.code for s in session.scalars(select(SignalSource))}
    out = []
    for series in session.scalars(select(SignalSeries).order_by(SignalSeries.source_id, SignalSeries.key)):
        series.source_code = sources[series.source_id]
        days = list(session.scalars(select(SignalObservation.observed_on).where(
            SignalObservation.series_id == series.id).order_by(SignalObservation.observed_on)))
        status = "never fetched" if series.last_success_at is None else "ok"
        if series.last_error:
            status = f"last attempt failed: {series.last_error}"
        if not days or series.is_forecast:
            out.append(SeriesGaps(series.key, series.source_code, len(days), days[0] if days else None,
                                  days[-1] if days else None, 0, 0, status=status))
            continue
        start = BACKFILL_START if series.frequency.value != "monthly" else BACKFILL_START.replace(day=1)
        expected = _expected_days(series, start, days[-1])
        have = set(days)
        missing = [d for d in expected if d not in have]
        if series.frequency.value == "monthly":
            step = lambda a, b: (b.year * 12 + b.month) - (a.year * 12 + a.month) == 1  # noqa: E731
        elif series.source_code == "fred":
            step = lambda a, b: (b - a).days == 1 or (a.weekday() == 4 and (b - a).days == 3)  # noqa: E731
        else:
            step = lambda a, b: (b - a).days == 1  # noqa: E731
        out.append(SeriesGaps(series.key, series.source_code, len(days), days[0], days[-1], len(expected),
                              len(missing), _ranges(missing, step), status))
    return out


@dataclass
class NewsCoverage:
    category: str
    headlines: int
    first: date | None
    last: date | None
    empty_months: list[str]
    capped_windows: int


def news_coverage(session: Session, categories: list[str]) -> list[NewsCoverage]:
    capped: dict[str, int] = {}
    for detail in session.scalars(select(SignalFetch.detail).where(SignalFetch.detail.is_not(None))):
        for item in (detail or {}).get("capped", []):
            category = item.split("|", 1)[0]
            capped[category] = capped.get(category, 0) + 1
    out = []
    for category in categories:
        stamps = list(session.scalars(select(NewsItem.published_at).join(NewsItemCategory).where(
            NewsItemCategory.category == category)))
        months = {f"{s:%Y-%m}" for s in stamps}
        empty = []
        cursor = BACKFILL_START.replace(day=1)
        last = max(stamps).date() if stamps else None
        while last and cursor <= last:
            if f"{cursor:%Y-%m}" not in months:
                empty.append(f"{cursor:%Y-%m}")
            cursor = (cursor + timedelta(days=32)).replace(day=1)
        out.append(NewsCoverage(category, len(stamps), min(stamps).date() if stamps else None, last, empty,
                                capped.get(category, 0)))
    return out


def format_status(session: Session, categories: list[str]) -> str:
    lines = []
    for src in session.scalars(select(SignalSource).order_by(SignalSource.id)):
        lines.append(f"{src.code}: last status {src.last_status.value if src.last_status else 'never run'}, "
                     f"last success {src.last_success_at:%Y-%m-%d %H:%M} UTC" if src.last_success_at else
                     f"{src.code}: last status {src.last_status.value if src.last_status else 'never run'}, "
                     "never succeeded")
        if src.last_error:
            lines.append(f"  last error: {src.last_error}")
    lines.append("")
    lines.append(f"{'series':34} {'rows':>6} {'first':>10} {'last':>10} {'expected':>8} {'gaps':>5}  longest gaps")
    for g in series_gaps(session):
        ranges = ", ".join(f"{a}" if a == b else f"{a}..{b}" for a, b in g.ranges[:3])
        more = f" (+{len(g.ranges) - 3} more)" if len(g.ranges) > 3 else ""
        lines.append(f"{g.key:34} {g.rows:>6} {str(g.first or '-'):>10} {str(g.last or '-'):>10} "
                     f"{g.expected or '-':>8} {g.missing if g.expected else '-':>5}  {ranges}{more}"
                     + ("" if g.status == "ok" else f"  [{g.status}]"))
    lines.append("")
    total = session.scalar(select(func.count()).select_from(NewsItem)) or 0
    lines.append(f"news: {total} headlines in all")
    for c in news_coverage(session, categories):
        empty = ", ".join(c.empty_months[:6]) + (f" (+{len(c.empty_months) - 6})" if len(c.empty_months) > 6 else "")
        lines.append(f"  {c.category:24} {c.headlines:>5} headlines, {c.first or '-'} .. {c.last or '-'}; "
                     f"months with none: {empty or 'none'}; capped windows: {c.capped_windows}")
    return "\n".join(lines)
